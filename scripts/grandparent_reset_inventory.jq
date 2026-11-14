# Closed projections and metadata comparisons; no product/durable semantics.
def insist($condition): if $condition then . else error("metadata-refused") end;
def hexid: type=="string" and test("^[0-9a-f]{64}$");
def imageid: type=="string" and test("^sha256:[0-9a-f]{64}$");
def text: type=="string" and length<=256 and test("^[A-Za-z0-9_./:@+ -]*$");
def own($expected): . as $actual | all($expected|to_entries[]; $actual[.key]==.value);
def volume_names: $manifest[0].volume_candidates|map(.name);
def candidate_ids: $manifest[0].container_candidates|map(.id);
def expected_ports($role):
  if $role=="cpk" then [{container_port:"8080/tcp",host_ip:"127.0.0.1",host_port:"18163"}]
  elif $role|startswith("website") then [{container_port:"8080/tcp",host_ip:"127.0.0.1",host_port:"18164"}]
  else [] end;
def wanted_volume: . as $name | volume_names | index($name)!=null;
def named_mounts:
  [.mounts[],.configured_mounts[]|select(.type=="volume")|.name] +
  [(.binds//[])[]|split(":")[0]|select(wanted_volume)] | unique;
def refs: (.volumes_from//[])|map(split(":")[0]);
def port_rows:
  [(.//{}|to_entries[]) as $entry|($entry.value//[])[]|
   {container_port:$entry.key,host_ip:.HostIp,host_port:.HostPort}];
def checked_ownership: insist(type=="object" and length<=5 and all(.[]; .==null or text));
def resolve($containers;$ref):
  [$containers[]|select(.id==$ref or .name==("/"+$ref) or .name==$ref)|.id] |
  if length==1 then .[0] else error("metadata-refused") end;
def closure($containers;$ref;$seen):
  resolve($containers;$ref) as $first |
  reduce range(0;128) as $_ ({seen:[],todo:[$first]};
    if (.todo|length)==0 then . else
      .todo[0] as $id | .todo=.todo[1:] | .seen+=[$id] | .seen as $known |
      .todo=((.todo+[$containers[]|select(.id==$id)|.volumes_from[]|resolve($containers;.)]) |
        unique | map(select(. as $next|$known|index($next)==null)))
    end) |
  insist((.todo|length)==0) | .seen;
def network_closure($containers;$id;$seen):
  if $seen|index($id)!=null then error("metadata-refused") else
    ($containers[]|select(.id==$id)) as $c |
    if $c.network_mode|startswith("container:") then
      resolve($containers;($c.network_mode|ltrimstr("container:"))) as $next |
      [$id]+network_closure($containers;$next;$seen+[$id])
    else [$id] end
  end;
def target_network($c):
  $manifest[0].network_candidate as $n |
  ($c.network_mode==$n.id or $c.network_mode==$n.name or
   any($c.networks[]; .id==$n.id or .name==$n.name));
def category:
  split("/")|last|
  if IN("Docker","com.docker.backend") then "docker-runtime"
  elif IN("cloudflared","nginx","caddy","traefik","haproxy","ssh","sshd","socat","frpc","frps","tailscaled") then "forwarder"
  else "other" end;
def owner_checks($records):
  [$records[]|select(.kind=="processes")|.owners[]] as $processes |
  [$records[]|select(.kind=="listener")|. as $listener|.owners[] as $owner|
    [$processes[]|select(.pid==$owner.pid)] as $found |
    {port:$listener.port,pid:$owner.pid,lsof_category:$owner.category,
     ps_category:(if ($found|length)==1 then $found[0].category else "unknown" end),
     ps_status:(if ($found|length)==0 then "missing" elif ($found|length)==1 then "unique" else "ambiguous" end)}];
def target_relations($containers;$c):
  (try closure($containers;$c.id;[]) catch null) as $storage |
  (try network_closure($containers;$c.id;[]) catch null) as $network |
  {id:$c.id,
   declared_target_volumes:[volume_names[] as $volume|
     select(($c.named_volumes|index($volume)!=null) or
       any($containers[];(.id as $id|($storage//[])|index($id)!=null) and (.named_volumes|index($volume)!=null)))|$volume],
   target_network:(target_network($c) or any($containers[];(.id as $id|($network//[])|index($id)!=null) and target_network(.))),
   target_ports:[$c.effective_ports[],$c.configured_ports[]|select(.host_port=="18163" or .host_port=="18164")]|unique,
   unresolved_reference:($storage==null or $network==null)};

if $mode=="ids" then
  insist(type=="array" and length<=128 and length==(unique|length) and all(.[];hexid))
elif $mode=="sets" then
  insist((.ids|length<=128 and length==(unique|length) and all(.[];hexid)) and
    (.volumes|length<=64 and length==(unique|length) and all(.[];text)) and
    (.networks|length<=16 and length==(unique|length) and all(.[];hexid))) |
  . as $sets |
  insist(all($manifest[0].container_candidates[]|select(.presence_required); .id as $id|$sets.ids|index($id)!=null)) |
  insist((.volumes|sort)==(volume_names|sort) and .networks==[$manifest[0].network_candidate.id]) |
  .ids|=sort | .volumes|=sort | .networks|=sort
elif $mode=="container" then
  insist((.id|hexid) and (.name|text) and (.image|imageid) and
    (.state|IN("running","exited","created")) and
    ([.running,.paused,.restarting,.dead]|all(type=="boolean")) and
    .paused==false and .restarting==false and .dead==false and
    (.network_mode|text) and (.stop_signal==null or (.stop_signal|text)) and
    (.mounts|type=="array" and length<=64) and (.configured_mounts|type=="array" and length<=64) and
    (.networks|type=="array" and length<=32) and
    ((.binds//[])|type=="array" and length<=64 and all(.[];type=="string" and length<=4096)) and
    ((.volumes_from//[])|type=="array" and length<=64 and all(.[];text))) |
  .ownership|=checked_ownership |
  insist(all(.mounts[],.configured_mounts[]; (.type|IN("volume","bind","tmpfs")) and
    (if .type=="volume" then (.name|text) else .name==null end)) and
    all(.networks[];(.name|text) and (.id=="" or (.id|hexid)) and
      ((.aliases//[])|type=="array" and length<=64 and all(.[];text)))) |
  (.ports|port_rows) as $effective | (.configured_ports|port_rows) as $configured |
  insist(($effective|length)<=64 and ($configured|length)<=64 and
    all($effective[],$configured[]; (.container_port|test("^[0-9]+/(tcp|udp|sctp)$")) and
      (.host_port|test("^[0-9]+$")) and (.host_ip|test("^[0-9a-fA-F:.]*$")))) |
  {kind:"container",id,name,image,state,running,stop_signal,ownership,network_mode,networks,
   named_volumes:named_mounts,volumes_from:refs,
   effective_ports:$effective,configured_ports:$configured}
elif $mode=="volume" then
  . as $v | insist(any($manifest[0].volume_candidates[]; . as $expected | .name==$v.name and ($v.ownership|own($expected.expected_ownership)))) |
  insist(.driver=="local" and .scope=="local" and .options_empty==true) |
  {kind:"volume",name,driver,scope,ownership}
elif $mode=="network" then
  $manifest[0].network_candidate as $n |
  insist(.id==$n.id and .name==$n.name and (.ownership|own($n.expected_ownership)) and
    .driver=="bridge" and .scope=="local" and .ingress==false and .config_only==false and
    .config_from_empty==true and (.internal|type=="boolean") and (.attachable|type=="boolean") and
    (.members|length<=128 and length==(unique|length) and all(.[];hexid))) |
  {kind:"network",id,name,ownership,members,internal,attachable}
elif $mode=="image" then
  . as $image | ($plan[0].ordered_queries[]|select(.stage=="five-fresh-image-cache-checks")|.images[]|select(.reference==$image.reference)) as $expected |
  insist(.id==$expected.expected_id and .os=="linux" and .architecture=="amd64" and
    ((.repo_digests//[])|type=="array" and length<=32 and all(.[];type=="string" and length<=512)) and
    (if $expected.repo_digest_required then (.repo_digests|index($expected.reference)!=null) else true end) and
    (.user==null or (.user|text)) and (.stop_signal==null or (.stop_signal|text))) |
  {kind:"image",reference,id,os,architecture,user,stop_signal,exact_reference_verified:true}
elif $mode=="listener" then
  insist(.port=="18163" or .port=="18164") |
  .port as $port | [.lines[]|select(length>0)] as $lines |
  insist(if ($lines|length)==0 then .no_match==true else .no_match==false end) |
  insist(($lines|length)<=512 and all($lines[];length<=256 and
    test("^(p[0-9]+|c[^[:cntrl:]]+|f[0-9]+[a-zA-Z]*|n[^[:cntrl:]]+)$"))) |
  (reduce $lines[] as $line ({owners:[],current:null};
    if $line|startswith("p") then .current=($line|ltrimstr("p"))|
      .owners+=[{pid:.current,category:"unknown"}]
    elif $line|startswith("c") then insist(.current!=null)|
      .owners[-1].category=($line|ltrimstr("c")|category)
    else . end)) as $parsed |
  {kind:"listener",port:$port,visibility:"current-user-only",owners:$parsed.owners,
   status:(if ($lines|length)==0 then "no-visible-listener" else "visible-listener" end),
   address_classes:[$lines[]|select(startswith("n"))|
     if .==("n127.0.0.1:"+$port) or .==("n[::1]:"+$port) then "loopback"
     elif .==("n*:"+$port) or .==("n[::]:"+$port) or .==("n0.0.0.0:"+$port) then "all-interfaces"
     else "unknown" end]|unique} |
  insist(all(.address_classes[];.=="loopback") and
    (if ($lines|length)>0 then (.owners|length)>0 and (.address_classes|length)>0 else true end))
elif $mode=="processes" then
  [.lines[]|select(test("[^[:space:]]"))] as $lines |
  insist(($lines|length)>0 and ($lines|length)<=8192 and all($lines[];length<=4096 and test("^[[:space:]]*[0-9]+[[:space:]]+[0-9]+[[:space:]]+.+$"))) |
  [$lines[]|capture("^[[:space:]]*(?<pid>[0-9]+)[[:space:]]+(?<ppid>[0-9]+)[[:space:]]+(?<comm>.+)$")|
    {pid,category:(.comm|category)}] as $owners |
  insist(($owners|map(.pid)|unique|length)==($owners|length)) |
  {kind:"processes",visible_count:($lines|length),owners:$owners,candidates:[$owners[]|select(.category!="other")]} |
  insist((.candidates|length)<=64)
elif $mode=="report" then
  . as $partial | try (
  . as $records | [$records[]|select(.kind=="sets")] as $sets |
  [$records[]|select(.kind=="container")] as $containers |
  [$records[]|select(.kind=="volume")] as $volumes |
  [$records[]|select(.kind=="network")] as $networks |
  [$records[]|select(.kind=="image")] as $images |
  insist(length>0 and .[0].kind=="admission" and .[-1].kind=="complete" and
    ($sets|length)==2 and $sets[0]==$sets[1] and
    ($containers|map(.id)|sort)==$sets[0].ids and
    ($volumes|map(.name)|sort)==(volume_names|sort) and
    $sets[0].volumes==(volume_names|sort) and
    ($networks|length)==1 and $sets[0].networks==[$manifest[0].network_candidate.id] and
    ($images|length)==5 and ($images|map(.reference)|unique|length)==5 and
    ([$records[]|select(.kind=="listener")|.port]|sort)==["18163","18164"] and
    ([$records[]|select(.kind=="processes")]|length)==1) |
  owner_checks($records) as $owner_checks |
  insist(all($owner_checks[];.ps_status=="unique" and .ps_category=="docker-runtime" and .lsof_category=="docker-runtime")) |
  [$manifest[0].container_candidates[] as $expected |
    [$containers[]|select(.id==$expected.id)] as $found |
    if ($found|length)==0 then
      insist($expected.presence_required==false) | {id:$expected.id,present:false,required:false}
    else $found[0] |
      insist(.name==("/"+$expected.name) and .image==$expected.image and (.ownership|own($expected.expected_ownership)) and
        (.configured_ports|sort)==(expected_ports($expected.role)|sort) and
        (if .running then (.effective_ports|sort)==(expected_ports($expected.role)|sort) else (.effective_ports|length)==0 end) and
        (if $expected.presence_required then true else .running==false and .state=="exited" end)) |
      {id,present:true,required:$expected.presence_required,identity_matches:true,state,stop_signal}
    end] as $targets |
  insist(all($containers[]; if .ownership["org.openj92.cpk.installation"]==$manifest[0].installation_id then
    .id as $id | candidate_ids|index($id)!=null else true end)) |
  insist(all($containers[]; . as $c | if (candidate_ids|index($c.id))==null then
    all(.effective_ports[],.configured_ports[];.host_port!="18163" and .host_port!="18164") else true end)) |
  [$containers[]|.id as $id|{id:$id,inherited:closure($containers;$id;[])}] as $storage |
  [volume_names[] as $volume |
    {volume:$volume,consumers:[$storage[] as $consumer |
      select(any($containers[]; (.id as $id|$consumer.inherited|index($id)!=null) and
        (.named_volumes|index($volume)!=null))) | $consumer.id]}] as $consumers |
  [$containers[] as $c | network_closure($containers;$c.id;[]) as $inherited |
    select(any($containers[]; (.id as $id|$inherited|index($id)!=null) and target_network(.))) | $c.id] as $network_consumers |
  insist(all($consumers[].consumers[],$network_consumers[],$networks[0].members[]; . as $id|candidate_ids|index($id)!=null)) |
  insist(all($networks[0].members[];. as $id|$containers|map(.id)|index($id)!=null)) |
  {schema:"cpk399.reset-inventory-observation.v1",status:"observed",approval_sha256:$approval_sha256,
   manifest_sha256:$action[0].manifest_sha256,plan_sha256:$action[0].plan_sha256,queries_sha256:$action[0].queries_sha256,
   source_commit:$source,started_epoch:$started,finished_epoch:$records[-1].finished,
   engine_matches:true,opening_closing_sets_equal:true,non_atomic:true,
   enumeration_counts:{containers:($containers|length),target_volumes:($volumes|length),target_networks:1},
   target_containers:$targets,declared_named_volume_consumers:$consumers,network_consumers:$network_consumers,
   volume_checks:$volumes,network_checks:$networks,image_cache:$images,
   listeners:[$records[]|select(.kind=="listener")],listener_owner_checks:$owner_checks,
   visible_processes:[$records[]|select(.kind=="processes")|del(.owners)],
   backing_path_bind_access:"unresolved",retirement_volume_exclusivity:"unproven",
   can_satisfy_retirement_exclusivity:false,external_routing:"unresolved",
   hidden_or_custom_forwarders:"unresolved",retry:false,service_mutation:false,credential_use:false,provider_read:false}
  ) catch (
    [$partial[]|select(.kind=="container")] as $partial_containers |
    [$partial_containers[]|target_relations($partial_containers;.)] as $relations |
    {
    schema:"cpk399.reset-inventory-observation.v1",status:"HOLD",approval_sha256:$approval_sha256,source_commit:$source,
    manifest_sha256:$action[0].manifest_sha256,plan_sha256:$action[0].plan_sha256,queries_sha256:$action[0].queries_sha256,
    stage:([$partial[]|select(.kind=="failure")|.stage]|last//"comparison"),failure_category:"metadata-refused",
    observed_counts:{containers:([$partial[]|select(.kind=="container")]|length),volumes:([$partial[]|select(.kind=="volume")]|length),
      networks:([$partial[]|select(.kind=="network")]|length),images:([$partial[]|select(.kind=="image")]|length)},
    relevant_foreign_containers:[$relations[]|. as $r|select((candidate_ids|index($r.id))==null)|
      select((.declared_target_volumes|length)>0 or .target_network or (.target_ports|length)>0)|del(.unresolved_reference)],
    unresolved_reference:any($relations[];.unresolved_reference),listener_owner_checks:owner_checks($partial),
    complete:false,non_atomic:true,backing_path_bind_access:"unresolved",external_routing:"unresolved",
    retirement_volume_exclusivity:"unproven",can_satisfy_retirement_exclusivity:false,
    retry:false,service_mutation:false,credential_use:false,provider_read:false})
else error("mode-refused") end
