Source: [Dockerfile](../../../../products/hello_server/Dockerfile).

The recipe remains Python3.12, numeric Hello UID10002 and internal port8000.
SDK[verification] is installed from the canonical exact SDK commit through
apply_coordinates.py. Core is selected by SDK's reviewed exact dependency.
It copies product source and starts the product-owned fixed-file receiver; no
default keys, authority or configuration file is baked into the image.

The existing published descriptor/digest does not contain this wrapper. #184's
normal suite checks generated installation and source integration, not a new
Hello image. #191 owns immutable build qualification, account/configuration
mount evidence and catalogue adoption. No image is published by this recipe edit.
