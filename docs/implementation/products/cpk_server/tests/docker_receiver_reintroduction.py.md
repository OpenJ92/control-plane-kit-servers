Source: [docker_receiver_reintroduction.py](../../../../../products/cpk_server/tests/docker_receiver_reintroduction.py).

The initial #255 target-red checkpoint relocates the existing pure node-map
construction unchanged, before correcting its containment ordering. Core codecs
sort node dictionaries but runtime children retain order. Removal must filter
the selected children tuple; fresh introduction must append only new children.
The focused tests govern that input law; no runtime or owner state is simulated.
This checkpoint is intentionally unvalidated and is not lifecycle acceptance.
