Source: products/cpk_server/Dockerfile.bootstrap-driver.

The complete local installer uses only reviewed Git exports and a verified local
controller base. Copied verifier/import modules, public cohort proof and maintained
public fixtures live under /usr/share/cpk-bootstrap-driver. Before sealing, the
recipe explicitly normalizes this public tree to owner rw/group-other r, adding
execute only for directories or already executable files. Generated public proof
and package installation use image umask022. This removes dependence on a private
host umask without making public proof writable to non-root users.

Attempt01 at37e exposed copied0600 public files under host umask077. UID0 schema
verification passed; the non-root verifier could not start, and a separately
authorized direct UID10001 production call refused unreadable cohort metadata.
The installed package/SQL files were already readable; they need no chmod.
This fix changes no host or private custody modes, source/RECORD content, runtime
logic or permission boundary. The one authorized further attempt uses fresh02
coordinates and must prove both UIDs plus the host-UID offline CLI, then pause.
