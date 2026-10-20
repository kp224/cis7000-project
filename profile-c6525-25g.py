"""One bare-metal c6525-25g with Ubuntu 22.04 for CFS restoration tests.

Instructions:
Choose the CloudLab Utah cluster. Once the node is ready, connect using
the SSH command in the experiment's List View.

Prepare and patch the kernel sources, then build with:
NODE_TYPE=c6525-25g bash scripts/build-kernels.sh
The original Ubuntu kernel remains available after test-kernel installation.
"""

import geni.portal as portal
import geni.rspec.pg as rspec

request = portal.context.makeRequestRSpec()
node = request.RawPC("cfs-test")
node.hardware_type = "c6525-25g"
node.disk_image = "urn:publicid:IDN+emulab.net+image+emulab-ops//UBUNTU22-64-STD"

portal.context.printRequestRSpec()
