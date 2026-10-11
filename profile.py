"""One bare-metal m510 with Ubuntu 22.04 for CFS restoration tests.

Instructions:
Choose the CloudLab Utah cluster. Once the node is ready, connect using
the SSH command in the experiment's List View.

This profile boots the standard Ubuntu kernel. We will build and install
our CFS and EEVDF kernels after login, keeping the original kernel available.
"""

import geni.portal as portal
import geni.rspec.pg as rspec

request = portal.context.makeRequestRSpec()
node = request.RawPC("cfs-test")
node.hardware_type = "m510"
node.disk_image = "urn:publicid:IDN+emulab.net+image+emulab-ops//UBUNTU22-64-STD"

portal.context.printRequestRSpec()
