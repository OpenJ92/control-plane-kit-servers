Source: [Dockerfile](../../../../products/http_active_router/Dockerfile).
Maintain with the router's generated dependency recipe.

The Python3.12 image installs canonical SDK[verification], including its actual
Core contract dependency, through apply_coordinates.py ownership. It preserves
UID10003, PORT8000 and EXPOSE8000 and copies only its product source. No trusted
configuration/default keys are baked in. Root package SDK installation alone
would not prove this runtime dependency. The recipe is source evidence; this
slice does not build/qualify/publish a new router digest or alter the historical
product descriptor. Candidate qualification belongs to191.
