# SDN DNS Load Balancer

Computer Networks mini project (UE25CS243A): a DNS-like name resolution service over UDP, where a Ryu SDN controller caches answers and load-balances queries across two backend servers.

## Team
| Name | SRN |
| --- | --- |
| Vishesh M | PES1UG25AM451 |
| Yuvaraj Karam | PES1UG25AM458 |
| Agreya Tejas | PES1UG25AM463 |

## Features
- **Query interception:** the switch sends every UDP packet on port 5555 to the controller (Packet-In).
- **In-memory cache:** the controller answers repeated queries itself (60 s TTL), so no backend is contacted.
- **Round-robin load balancing:** on a cache miss, the query is rewritten (SetField) towards ds1 or ds2.
- **Link failover:** PortStatus events remove a failed server from the pool and re-add it on recovery.
- **Client timeout and retry:** 2 s timeout, up to 3 attempts.

## Topology
```
c1 (10.0.0.1) --port1-- s1 (OVS) --port2-- ds1 (10.0.0.10)
                          |
                          +--port3-- ds2 (10.0.0.11)
Controller: Ryu, OpenFlow 1.3, 127.0.0.1:6633
Virtual responder for cache hits: 10.0.0.254
```

## Files
| File | Purpose |
| --- | --- |
| `topology.py` | Mininet topology (1 switch, 1 client, 2 servers) |
| `dns_server.py` | Backend UDP DNS server (500 ms simulated lookup) |
| `dns_client.py` | UDP client with timeout and retries |
| `ryu_loadbalancer.py` | Ryu controller: cache, round-robin, failover |

## Requirements
- Ubuntu with Mininet, Open vSwitch and xterm
- Ryu 4.34 in a Python 3.9 virtual environment (Ryu does not build on newer Python)

```bash
sudo apt install -y mininet openvswitch-switch xterm
uv venv --seed --python 3.9 ~/ryu-env
source ~/ryu-env/bin/activate
pip install "setuptools==65.5.0" wheel pbr
pip install --no-build-isolation "eventlet==0.30.2" ryu
```

## Run
**Terminal 1 (controller):**
```bash
source ~/ryu-env/bin/activate
ryu-manager ryu_loadbalancer.py
```
**Terminal 2 (network, no venv):**
```bash
sudo mn -c
sudo python3 topology.py
```
**At the `mininet>` prompt:**
```
xterm ds1 ds2 c1
```
- ds1 window: `python3 dns_server.py 10.0.0.10`
- ds2 window: `python3 dns_server.py 10.0.0.11`
- c1 window: run the tests below

In the xterm windows, `~` means `/root`, so use full paths.

## Tests
1. **Caching and round-robin:** `web.local` (ds1, ~500 ms), `mail.local` (ds2, ~500 ms), `web.local` again (controller, ~6 ms).
2. **Failover:** `link s1 ds1 down`, then query `ftp.local` and `db.local`. Both go to ds2.
3. **Timeout:** stop the ds2 server, then query `test.local`. The client times out 3 times.

## Results
| Query | Answered by | Latency |
| --- | --- | --- |
| web.local (miss) | ds1 | ~516 ms |
| mail.local (miss) | ds2 | ~510 ms |
| web.local (hit) | controller | ~6 ms |

Screenshots are in `screenshots/`.

## Limitations
- Only link failure is detected, not a crashed server process.
- Every query passes through the controller.
- Plain-text protocol, fixed 60 s TTL, single switch with hard-coded ports.
- NXDOMAIN answers are not cached.
