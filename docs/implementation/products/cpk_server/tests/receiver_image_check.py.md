Source: [receiver_image_check.py](../../../../../products/cpk_server/tests/receiver_image_check.py).
Maintain with the #163 focused image smoke and unchanged product recipe.

Runs inside the built product image with network disabled and only this helper
and public coordinates mounted read-only. It checks installed direct-URL
metadata for Core, Operations, Interpreters and SDK against the selected public
archive coordinates, imports the actual image's CPK server from its packaged
source directory, and runs installed `pip check`. It prints only bounded public
origin/status data and a fixed error on failure. This is an inspection process;
the later runtime proof separately requires the actual default entrypoint.
