"""Network latency between services.

Symptoms:
- multiple services show elevated latency together
- failure flag network_delay on several nodes
- traces show large gaps between client send and server receive

Remediation:
- Remove injected network delay (dev)
- Check DNS and compose network
- Restart is optional and may not help a network-level delay
"""
