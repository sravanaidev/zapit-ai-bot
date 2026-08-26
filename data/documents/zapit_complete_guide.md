# Zapit 4.4 — Complete Administration, Operations, and Troubleshooting Guide

**Document Version:** 2.0
**Product Version:** 4.4
**Build:** Go 1.26.5, GOFIPS140=latest, garble v0.16.0
**Date:** July 2026
**Classification:** Confidential

---

## Table of Contents

1. Product Overview
2. Architecture
3. Encryption and Security Model
4. Pre-Installation Checklist
5. Installation
6. Post-Installation Verification
7. Configuration Reference
8. SSH Key Setup
9. Service Management
10. Commands Reference
11. Transfer Examples
12. Congestion Control Modes
13. Heartbeat and Health Checks
14. Monitoring and Log Management
15. Performance Tuning
16. Capacity Planning
17. Security Hardening
18. Backup and Disaster Recovery
19. Upgrade and Rollback
20. Uninstall
21. Error Code Reference (complete)
22. Troubleshooting Guide (complete)
23. RPM Package Management
24. FAQ
25. Appendix A — verify.sh Script
26. Appendix B — Sample nodes.conf
27. Appendix C — Firewall Rules
28. Appendix D — Quick Reference Card

---

## 1. Product Overview

Zapit is an enterprise-grade file transfer solution that uses UDP for high-throughput delivery with AES-256-GCM encryption. It is designed for organisations requiring secure, high-speed movement of large files between servers in regulated industries including financial services, healthcare, government, and any environment handling sensitive data.

### 1.1 Key Capabilities

Zapit provides encrypted transfers using AES-256-GCM with hardware-accelerated AES-NI via Go's native FIPS 140-3 crypto module (GOFIPS140). The proprietary SPRINT+ (Scalable Pacing Reactive Increase Network-aware Tuning) congestion control algorithm offers three operating modes for different network conditions. A compact manifest format enables automatic transfer resume after failures without retransmitting completed data. Full job management supports submit, cancel, hold, release, restart, and purge operations. Binary obfuscation via garble protects intellectual property in distributed packages. All files reside under a single ZAPIT_HOME directory for clean deployment and easy migration.

### 1.2 Tested Performance

15 GB transferred in 2 minutes 2 seconds at 132 MB/s sustained throughput. Zero retries, zero data corruption, full checksum verification passed. Tested on AWS c5.xlarge instances with gp3 EBS storage and 10 Gbps networking at 0.1ms round-trip latency. All three congestion modes (AIMD, SPRINT+, SPRINT+ Dedicated) achieved identical throughput, confirming that disk I/O is the limiting factor on standard hardware.

### 1.3 Supported File Types

Zapit transfers any file type. It reads raw bytes and sends them without inspecting content. Binary files, database exports, CSV, PDF, log files, archives, images, video, encrypted files, files with no extension, empty files, and files exceeding 1 TB are all supported identically.

### 1.4 Supported Platforms

Any Linux distribution with glibc 2.17 or later, including RHEL 7, 8, and 9, CentOS 7 and later, Amazon Linux 2 and 2023, Rocky Linux 8 and later, AlmaLinux 8 and later, Ubuntu 18.04 and later, Debian 10 and later, and SUSE Linux Enterprise 15 and later.

---

## 2. Architecture

### 2.1 Components

**zapitd** is the daemon process that runs 24/7 as a systemd service. It listens for incoming transfers on the SSH control port, accepts CLI commands via a Unix socket, manages the job queue, and handles both sending and receiving of files. There is no limit on concurrent transfers — the daemon processes as many simultaneous jobs as the server's CPU and memory allow.

**zapit** is the command-line interface used by operators to submit transfers, list jobs, cancel or restart operations, and manage nodes.

**zapit-reader** is a setuid binary that enables transfers using a different OS user for reading source files. This allows multiple teams sharing the same server to transfer files from their own directories without granting the zapit service account access to all directories.

**zapit-recv** is the standalone receiver binary for direct transfers without the daemon.

**zapit-send** is the standalone sender binary for direct transfers without the daemon.

### 2.2 Network Architecture

Each transfer uses two channels. The SSH control channel runs over TCP (default port 2222, configurable) and handles authentication, encryption key exchange, transfer metadata, acknowledgements, and job control messages. The UDP data channel (default port 9000, configurable) carries the encrypted file data as chunked fragments. Both ports are fully configurable per node in nodes.conf.

### 2.3 Directory Structure

All files reside under a single root directory defined by the ZAPIT_HOME environment variable. ZAPIT_HOME is mandatory — the program exits with a clear error if it is not set.

```
$ZAPIT_HOME/
  bin/           Binaries (zapitd, zapit, zapit-reader, zapit-recv, zapit-send)
  nodes/         Configuration (nodes.conf, nodes.conf.example)
  log/           Transfer logs and audit logs (one file per day)
  manifest/      Chunk status files for resume
  security/      SSH host key, authorized keys, transfer keys, known hosts
  run/           Unix socket (zapitd.sock) for CLI-daemon communication
  doc/           README and LICENSE
```

The only file outside ZAPIT_HOME is /etc/sysconfig/zapit, which stores the ZAPIT_HOME path for systemd. This file survives reboots, OS patching, RPM upgrades, and RPM removal.

### 2.4 Transfer Flow Summary

When a transfer is submitted, the daemon performs a source file stability check (stat, wait 2 seconds, stat again — fails if file is being written). It then plans the transfer by calculating chunks (file size divided into 1 MB chunks), connects to the receiver via SSH, generates a random AES-256-GCM key in memory, exchanges the key over the encrypted SSH channel, and begins sending encrypted chunks over UDP. Each chunk is read from disk, hashed inline (SHA-256 running hash for single-pass efficiency), encrypted with AES-256-GCM (unique nonce per chunk), fragmented into ~730 UDP packets (~1400 bytes each, MTU-safe), and sent using timer-based pacing. The receiver collects fragments, verifies the GCM authentication tag (rejects tampered data), writes to a temp file, and sends ACKs. After all chunks are delivered, a post-transfer stability check verifies the source file was not modified during transfer. The receiver renames the temp file to the final destination and calls fsync.

---

## 3. Encryption and Security Model

### 3.1 SSH Control Channel

The control channel uses Go's crypto/ssh library with the FIPS 140-3 crypto module. Supported ciphers include aes128-gcm@openssh.com, aes256-gcm@openssh.com, chacha20-poly1305@openssh.com, aes128-ctr, aes192-ctr, and aes256-ctr. Supported MACs include hmac-sha2-256, hmac-sha2-512, hmac-sha2-256-etm@openssh.com, and hmac-sha2-512-etm@openssh.com. Cipher and MAC selection is negotiated automatically during the SSH handshake.

### 3.2 UDP Data Channel

The data channel uses AES-256-GCM exclusively. This is intentional and not configurable. AES-256-GCM is an AEAD cipher (Authenticated Encryption with Associated Data) — the MAC is built into the encryption. Each chunk includes a 16-byte GCM authentication tag that provides both confidentiality and integrity. A random 256-bit key is generated per transfer using NIST SP 800-90A DRBG (FIPS-approved). The key is exchanged over the encrypted SSH channel and exists only in memory — never written to disk. Each chunk uses a unique 12-byte nonce (prefix plus chunk counter).

### 3.3 UDP Has No Built-In Security

Raw UDP provides no authentication, no encryption, and no integrity checking. Zapit adds all three layers: SSH authentication (only authorised senders connect), AES-256-GCM encryption (data is unreadable without the key), and GCM auth tags (tampered packets are rejected). An attacker observing the network sees only random encrypted bytes.

### 3.4 FIPS 140-3 Compliance

Zapit is built with GOFIPS140=latest, which enables Go's native FIPS 140-3 crypto module. This provides FIPS self-tests on startup (AES, SHA-256, HMAC, DRBG), integrity verification of the FIPS module code, and NIST-approved DRBG for all random number generation. The FIPS module adds approximately 8ms to daemon startup and 1ms per transfer — negligible overhead.

---

## 4. Pre-Installation Checklist

### 4.1 System Requirements

| Requirement | Minimum | Recommended |
|---|---|---|
| Operating System | Any Linux, glibc 2.17+ | RHEL 8+, Amazon Linux 2023 |
| CPU | 2 cores | 4+ cores |
| RAM | 4 GB | 8+ GB |
| Disk | 10 GB + transfer file space | SSD recommended |
| Network | TCP + UDP between servers | Dedicated link for best speed |

### 4.2 Checklist

```
[ ] Root or sudo access on the server
[ ] ZAPIT_HOME directory path decided (e.g. /opt/zapit)
[ ] Disk space available at ZAPIT_HOME
[ ] Disk space available at destination file location (2× file size during transfer)
[ ] TCP port for SSH control channel available (default 2222)
[ ] UDP port for data channel available (default 9000)
[ ] Firewall rules configured between source and destination servers
[ ] SSH key pair generated or planned
[ ] RPM file transferred to the server
[ ] Old zapit binaries removed from /usr/local/bin/ (if upgrading from pre-RPM)
```

### 4.3 Verify Port Availability

```
ss -tlnp | grep 2222
ss -ulnp | grep 9000
```

If either port is in use, choose a different port and configure it in nodes.conf.

---

## 5. Installation

### 5.1 Fresh Install

```
sudo rpm -ivh zapit-4.4-1.x86_64.rpm
```

The installer automatically creates all directories under ZAPIT_HOME, generates an ED25519 host key, creates an empty authorized_keys file, applies sysctl UDP buffer tuning, enables and starts the zapitd systemd service, sets zapit-reader setuid permissions, and adds the binary path to the system PATH.

### 5.2 Remove Pre-RPM Binaries (if upgrading from manual install)

```
sudo rm -f /usr/local/bin/zapit /usr/local/bin/zapitd /usr/local/bin/zapit-reader /usr/local/bin/zapit-recv /usr/local/bin/zapit-send
```

Old binaries at /usr/local/bin/ shadow the RPM-installed binaries and cause path confusion. Always remove them after RPM install.

### 5.3 Load Environment

```
source /etc/profile.d/zapit.sh
echo $ZAPIT_HOME
```

ZAPIT_HOME must show your installation path. New shell sessions load this automatically.

### 5.4 Custom Install Path

The default path is /opt/zapit. To use a different path:

```
echo "ZAPIT_HOME=/your/chosen/path" | sudo tee /etc/sysconfig/zapit
sudo systemctl restart zapitd
```

All subdirectories are created automatically.

### 5.5 Verify Installation

```
systemctl status zapitd
zapit list
which zapit
```

---

## 6. Post-Installation Verification

### 6.1 Full Verification Script

Run the verify.sh script (Appendix A) on each server:

```
bash verify.sh
```

Expected result: all checks pass. The script verifies all directories exist under ZAPIT_HOME, the host key was generated, the daemon is running and using the correct binary, the socket is accessible, no files exist at old hardcoded paths, and today's log file is being written.

### 6.2 Verify Sysctl Tuning

```
sysctl net.core.rmem_max
```

Expected: 268435456. If different:

```
sudo sysctl -p /etc/sysctl.d/99-zapit.conf
```

### 6.3 Verify FIPS Mode

```
strings $ZAPIT_HOME/bin/zapitd | grep -i fips | head -3
```

### 6.4 Verify Binary Obfuscation

```
strings $ZAPIT_HOME/bin/zapitd | grep -i "SPRINT+\|Scalable Pacing"
```

Expected: no output (strings are encrypted by garble).

### 6.5 Verify Socket Permissions

```
ls -la $ZAPIT_HOME/run/zapitd.sock
```

Expected: srw-rw-rw- (any user can connect to the daemon).

### 6.6 Clean Up Old Paths

After RPM install, remove any leftover files from pre-RPM installations:

```
sudo rm -rf /var/log/zapit /var/lib/zapit /var/run/zapit /etc/zapit
sudo rm -f /usr/local/bin/zapit* /usr/local/bin/zapitd
```

---

## 7. Configuration Reference

### 7.1 nodes.conf

Located at $ZAPIT_HOME/nodes/nodes.conf. Defines remote servers for file transfers.

```
nodes:
  PRODUCTION_SERVER_B:
    host:            10.0.1.50
    port:            2222
    udp_port:        9000
    encrypt:         true
    key:             /opt/zapit/security/transfer_key
    known_hosts:     /opt/zapit/security/known_hosts
    connect_timeout: 10
    chunk_mib:       1
    max_retries:     5
    window:          64
    max_window:      512
    rate_mbps:       0
    description:     Production Server B - London DC
```

Node names (e.g. PRODUCTION_SERVER_B) are local labels only. Different servers can name the same destination differently. The node name never leaves the sending server.

### 7.2 Configuration Fields

| Field | Required | Default | Description |
|---|---|---|---|
| host | Yes | — | IP address or hostname of remote server |
| port | No | 2222 | SSH control channel port |
| udp_port | No | 9000 | UDP data transfer port |
| encrypt | No | true | AES-256-GCM encryption |
| key | Yes | — | Path to SSH private key |
| known_hosts | No | — | Path to known_hosts for host verification |
| insecure | No | false | Skip host key verification (not for production) |
| connect_timeout | No | 10 | SSH connection timeout in seconds |
| chunk_mib | No | 1 | Chunk size in megabytes |
| max_retries | No | 5 | Maximum retransmission attempts per chunk |
| window | No | 64 | Initial congestion window |
| max_window | No | 512 | Maximum congestion window |
| rate_mbps | No | 0 | Rate limit in MB/s (0 = unlimited) |
| verify | No | false | End-to-end SHA-256 verification |
| congestion | No | aimd | Congestion mode: aimd or sprint |
| target_rate | No | — | Target rate for Dedicated mode (e.g. 500m, 1g) |
| source_user | No | — | OS user for reading source files |
| description | No | — | Human-readable description |

### 7.3 Environment File

Located at /etc/sysconfig/zapit:

```
ZAPIT_HOME=/opt/zapit
```

This is the ONLY file outside ZAPIT_HOME. It survives reboots, OS patching, RPM upgrades, and RPM removal.

### 7.4 Rate Format Reference

| Format | Speed |
|---|---|
| 100k | 100 KB/s |
| 10m | 10 MB/s |
| 100m | 100 MB/s |
| 500m | 500 MB/s |
| 1g | 1 GB/s |

---

## 8. SSH Key Setup

### 8.1 Generate Transfer Key (on sending server)

```
ssh-keygen -t ed25519 -f $ZAPIT_HOME/security/transfer_key -N "" -C "zapit-transfer"
```

### 8.2 Copy Public Key to Receiving Server

Display the key on the sender:

```
cat $ZAPIT_HOME/security/transfer_key.pub
```

Add it to the receiver (use tee for permission handling):

```
echo "PASTE_KEY_HERE" | sudo tee -a $ZAPIT_HOME/security/authorized_keys
```

### 8.3 Record Receiver Host Key

```
ssh-keyscan -p 2222 RECEIVER_IP 2>/dev/null | sudo tee $ZAPIT_HOME/security/known_hosts
```

### 8.4 Test Connectivity

```
zapit nodes test --node PRODUCTION_SERVER_B
```

---

## 9. Service Management

| Command | Description |
|---|---|
| sudo systemctl start zapitd | Start the daemon |
| sudo systemctl stop zapitd | Stop the daemon |
| sudo systemctl restart zapitd | Restart after configuration changes |
| sudo systemctl status zapitd | Check daemon status |
| sudo systemctl enable zapitd | Enable auto-start on boot |
| sudo systemctl disable zapitd | Disable auto-start |

### 9.1 View Service Configuration

```
systemctl cat zapitd
```

### 9.2 View Running Process

```
ps aux | grep zapitd | grep -v grep
```

Verify the process uses $ZAPIT_HOME/bin/zapitd and the correct flags.

### 9.3 View Journal

```
journalctl -u zapitd -f
journalctl -u zapitd --no-pager -n 50
```

---

## 10. Commands Reference

### 10.1 Transfer Commands

| Command | Description |
|---|---|
| zapit submit | Submit a new file transfer |
| zapit list | List all jobs with status and progress |
| zapit status --id JOB_ID | Detailed status of one job |
| zapit cancel --id JOB_ID | Cancel immediately |
| zapit stop --id JOB_ID | Stop gracefully — saves progress for resume |
| zapit hold --id JOB_ID | Pause a running transfer |
| zapit release --id JOB_ID | Resume a held transfer |
| zapit restart --id JOB_ID | Restart a failed or cancelled job |
| zapit restart --all-failed | Restart all failed jobs |
| zapit purge | Remove completed, failed, cancelled jobs from list |
| zapit drain | Finish running jobs, stop accepting new ones |

### 10.2 Node Commands

| Command | Description |
|---|---|
| zapit nodes list | Show all configured nodes |
| zapit nodes test --node NAME | Test connectivity and authentication |

### 10.3 Submit Flags

| Flag | Required | Description | Example |
|---|---|---|---|
| --src | Yes | Source file path | /data/file.bin |
| --dest | Yes | Destination file path | /data/received/file.bin |
| --node | Yes | Target node from nodes.conf | PRODUCTION_SERVER_B |
| --remote-user | Yes | SSH user on remote server | svc_zapit |
| --congestion | No | Mode: aimd or sprint | sprint |
| --target-rate | No | Target speed for Dedicated mode | 500m, 1g |
| --rate-limit | No | Hard rate ceiling | 800m |
| --verify | No | Enable end-to-end SHA-256 verification | |
| --source-user | No | Read source as different OS user | app_user |
| --encrypt | No | AES-256-GCM encryption (default: on) | |

---

## 11. Transfer Examples

### 11.1 Basic Transfer

```
zapit submit \
  --src /data/outgoing/report.csv \
  --dest /data/incoming/report.csv \
  --node PRODUCTION_SERVER_B \
  --remote-user svc_zapit
```

### 11.2 SPRINT+ Adaptive Mode

```
zapit submit \
  --src /data/outgoing/bigfile.bin \
  --dest /data/incoming/bigfile.bin \
  --node PRODUCTION_SERVER_B \
  --remote-user svc_zapit \
  --congestion sprint
```

### 11.3 SPRINT+ Dedicated (target 500 MB/s)

```
zapit submit \
  --src /data/outgoing/bigfile.bin \
  --dest /data/incoming/bigfile.bin \
  --node PRODUCTION_SERVER_B \
  --remote-user svc_zapit \
  --congestion sprint --target-rate 500m
```

### 11.4 With SHA-256 Verification

```
zapit submit \
  --src /data/outgoing/sensitive.dat \
  --dest /data/incoming/sensitive.dat \
  --node PRODUCTION_SERVER_B \
  --remote-user svc_zapit --verify
```

### 11.5 With Rate Limit

```
zapit submit \
  --src /data/file.bin \
  --dest /data/received/file.bin \
  --node SHARED_LINK_SERVER \
  --remote-user svc_zapit \
  --rate-limit 100m
```

### 11.6 With Source User

```
zapit submit \
  --src /app/data/export.csv \
  --dest /data/incoming/export.csv \
  --node PRODUCTION_SERVER_B \
  --remote-user svc_zapit \
  --source-user app_user
```

### 11.7 Maximum Speed

```
zapit submit \
  --src /data/large_dataset.bin \
  --dest /data/received/large_dataset.bin \
  --node DEDICATED_LINK \
  --remote-user svc_zapit \
  --congestion sprint --target-rate 1g
```

### 11.8 Monitor Progress

```
watch -n 1 zapit list
```

### 11.9 Restart Failed Transfer

```
zapit restart --id ZAPIT-20260614-00003
```

### 11.10 Restart All Failed

```
zapit restart --all-failed
```

---

## 12. Congestion Control Modes

### 12.1 AIMD (default)

Additive Increase, Multiplicative Decrease. Increases speed gradually (window += 1/window per ACK). Halves throughput on packet loss. No additional flags needed. Best for unknown or shared networks.

### 12.2 SPRINT+

Scalable Pacing Reactive Increase Network-aware Tuning. Monitors RTT (round-trip time) to detect congestion before packet loss. Reduces speed by 20% instead of 50%. Smoother than AIMD. Best for shared WAN links.

```
--congestion sprint
```

### 12.3 SPRINT+ Dedicated

Holds a fixed target speed you specify. Automatically falls back to adaptive mode on congestion and returns to the target when the network recovers. Best for dedicated links with known bandwidth. Set target rate to approximately 80% of link speed.

```
--congestion sprint --target-rate 500m
```

### 12.4 Mode Selection Guide

| Network Type | Recommended Mode | Flags |
|---|---|---|
| Unknown or shared | AIMD (default) | none |
| Shared WAN link | SPRINT+ | --congestion sprint |
| Dedicated link, known speed | SPRINT+ Dedicated | --congestion sprint --target-rate 500m |

### 12.5 Target Rate Guidelines

| Link Speed | Recommended Target |
|---|---|
| 100 Mbps | --target-rate 10m |
| 500 Mbps | --target-rate 50m |
| 1 Gbps | --target-rate 100m |
| 10 Gbps | --target-rate 1g |

---

## 13. Heartbeat and Health Checks

### 13.1 Daemon Status

```
systemctl status zapitd
```

### 13.2 Process Check

```
ps aux | grep zapitd | grep -v grep
```

### 13.3 Socket Check

```
ls -la $ZAPIT_HOME/run/zapitd.sock
```

### 13.4 Node Connectivity Test

```
zapit nodes test --node PRODUCTION_SERVER_B
```

### 13.5 Manual Network Tests

```
nc -zv RECEIVER_IP 2222 -w 3
nc -zuv RECEIVER_IP 9000 -w 3
```

### 13.6 SSH Authentication Test

```
ssh -p 2222 -i $ZAPIT_HOME/security/transfer_key user@RECEIVER_IP "echo OK"
```

### 13.7 Health Check Script (for monitoring tools)

```bash
#!/bin/bash
systemctl is-active zapitd >/dev/null 2>&1 || exit 1
test -S "$ZAPIT_HOME/run/zapitd.sock" || exit 1
zapit list >/dev/null 2>&1 || exit 1
exit 0
```

---

## 14. Monitoring and Log Management

### 14.1 Log Locations

| Log | Path | Contents |
|---|---|---|
| Application | $ZAPIT_HOME/log/zapit-zapitd-YYYY-MM-DD.log | Transfer details, encryption, congestion, speed, errors |
| Audit | $ZAPIT_HOME/log/zapit-audit-YYYY-MM-DD.log | Job state changes only (SUBMITTED, RUNNING, COMPLETE, FAILED) |

### 14.2 Common Log Queries

View today's log:
```
tail -f $ZAPIT_HOME/log/zapit-zapitd-$(date +%Y-%m-%d).log
```

Find transfer results:
```
grep "avg_rate\|COMPLETE\|FAILED" $ZAPIT_HOME/log/zapit-zapitd-$(date +%Y-%m-%d).log
```

Find errors:
```
grep "level=ERROR" $ZAPIT_HOME/log/zapit-zapitd-$(date +%Y-%m-%d).log
```

Find specific job:
```
grep "ZAPIT-20260614-00001" $ZAPIT_HOME/log/zapit-zapitd-$(date +%Y-%m-%d).log
```

Check encryption:
```
grep "AES-256-GCM\|encryption" $ZAPIT_HOME/log/zapit-zapitd-$(date +%Y-%m-%d).log
```

Check congestion mode:
```
grep "congestion controller" $ZAPIT_HOME/log/zapit-zapitd-$(date +%Y-%m-%d).log
```

Check stability check:
```
grep "stability" $ZAPIT_HOME/log/zapit-zapitd-$(date +%Y-%m-%d).log
```

Check verification:
```
grep "CHECKSUM\|verification" $ZAPIT_HOME/log/zapit-zapitd-$(date +%Y-%m-%d).log
```

### 14.3 Log Cleanup

Logs are created per day. Add a cron job for automatic cleanup:

```
0 2 * * * find $ZAPIT_HOME/log -name "*.log" -mtime +30 -delete
```

---

## 15. Performance Tuning

### 15.1 Transfer Speed Formula

```
Actual speed = minimum of (disk speed, network speed, encryption speed)

disk speed:       depends on storage type
network speed:    link bandwidth in Gbps × 125 = MB/s
encryption speed: ~3,000 MB/s per core (AES-NI + FIPS module)
```

### 15.2 Expected Transfer Times

| File Size | At 125 MB/s | At 300 MB/s | At 500 MB/s |
|---|---|---|---|
| 1 GB | 8 seconds | 3 seconds | 2 seconds |
| 10 GB | 82 seconds | 34 seconds | 20 seconds |
| 100 GB | 14 minutes | 6 minutes | 3 minutes |
| 500 GB | 1 hour 10 min | 29 minutes | 17 minutes |
| 1 TB | 2 hours 20 min | 58 minutes | 35 minutes |

### 15.3 Check Disk Speed

```
dd if=/dev/zero of=/tmp/disktest bs=1M count=1024 oflag=dsync
```

### 15.4 Check Sysctl Tuning

```
sysctl net.core.rmem_max net.core.wmem_max
```

Both should show 268435456. If not:

```
sudo sysctl -p /etc/sysctl.d/99-zapit.conf
```

---

## 16. Capacity Planning

### 16.1 Disk Space

Destination server needs free space equal to the file being transferred. During transfer, a temp file exists alongside any previous version — plan for 2× file size during the transfer window.

### 16.2 Bandwidth

For dedicated links, set target rate to 80% of capacity. For shared links, use SPRINT+ adaptive mode without a target rate.

### 16.3 Common Bottlenecks

| Storage Type | Typical Speed | 1 TB Transfer Time |
|---|---|---|
| gp3 EBS (default) | 125 MB/s | 2 hours 20 minutes |
| gp3 EBS (provisioned) | 500 MB/s | 35 minutes |
| SAN (typical bank) | 200-400 MB/s | 45 min - 1 hour 30 min |
| NVMe | 2,000+ MB/s | 9 minutes |

---

## 17. Security Hardening

### 17.1 Enable Host Key Verification

Always use known_hosts in production. Never use insecure: true in production.

### 17.2 File Permissions

```
chmod 600 $ZAPIT_HOME/security/host_key
chmod 600 $ZAPIT_HOME/security/transfer_key
chmod 644 $ZAPIT_HOME/security/authorized_keys
chmod 644 $ZAPIT_HOME/security/known_hosts
```

### 17.3 Restrict Authorized Keys

Only add keys from authorised sending servers. Review periodically and remove keys for decommissioned servers.

### 17.4 Restrict Firewall Rules

Allow traffic only from specific source IPs:

```
Allow TCP 2222 from: 10.0.1.10 (Server A) only
Allow UDP 9000 from: 10.0.1.10 (Server A) only
```

### 17.5 Verify zapit-reader Setuid

```
ls -la $ZAPIT_HOME/bin/zapit-reader
```

Expected: -rwsr-xr-x with root ownership. If incorrect:

```
sudo chown root:root $ZAPIT_HOME/bin/zapit-reader
sudo chmod 4755 $ZAPIT_HOME/bin/zapit-reader
```

---

## 18. Backup and Disaster Recovery

### 18.1 What to Back Up

| Item | Path | Priority |
|---|---|---|
| nodes.conf | $ZAPIT_HOME/nodes/nodes.conf | Critical |
| SSH host key | $ZAPIT_HOME/security/host_key | Critical |
| Authorized keys | $ZAPIT_HOME/security/authorized_keys | Critical |
| Transfer keys | $ZAPIT_HOME/security/transfer_key | Critical |
| Known hosts | $ZAPIT_HOME/security/known_hosts | Important |
| Environment file | /etc/sysconfig/zapit | Important |

### 18.2 Backup Command

```
tar czf zapit-backup-$(date +%Y%m%d).tar.gz \
  $ZAPIT_HOME/nodes/ \
  $ZAPIT_HOME/security/ \
  /etc/sysconfig/zapit
```

### 18.3 Restore

```
sudo systemctl stop zapitd
tar xzf zapit-backup-20260614.tar.gz -C /
sudo systemctl start zapitd
```

---

## 19. Upgrade and Rollback

### 19.1 Upgrade

```
sudo rpm -Uvh zapit-4.5-1.x86_64.rpm
```

Preserves nodes.conf, SSH keys, logs, and manifests.

### 19.2 Rollback

```
sudo rpm -Uvh --oldpackage zapit-4.4-1.x86_64.rpm
```

### 19.3 Check Version

```
rpm -q zapit
```

---

## 20. Uninstall

### 20.1 Remove Package (preserves data)

```
sudo rpm -e zapit
```

### 20.2 Full Removal

```
sudo rpm -e zapit
sudo rm -rf $ZAPIT_HOME
sudo rm -f /etc/sysconfig/zapit
```

---

## 21. Error Code Reference

### Preparation — ZAPIT-1xxx

| Code | Name | Description | Fix |
|---|---|---|---|
| ZAPIT-1001 | Source Validated | File exists and is readable | Informational |
| ZAPIT-1002 | Source Not Found | File does not exist | Verify path: ls -lh path |
| ZAPIT-1003 | Not Readable | Permission denied | chmod 644 or use --source-user |
| ZAPIT-1004 | Transfer Planned | Chunks calculated | Informational |
| ZAPIT-1005 | Chunk Too Large | Exceeds fragment limit | Use --chunk-mib 1 |
| ZAPIT-1006 | Manifest Saved | Written to disk | Informational |
| ZAPIT-1007 | Manifest Write Failed | Cannot write manifest | Check $ZAPIT_HOME/manifest permissions |
| ZAPIT-1008 | Key Generated | AES-256 key created in memory | Informational |
| ZAPIT-1009 | Resuming | Loading existing manifest | Informational |
| ZAPIT-1010 | Resume Not Found | No manifest for this ID | Run zapit list |
| ZAPIT-1011 | Checksum Computed | SHA-256 of source file | Informational |

### Connection — ZAPIT-2xxx

| Code | Name | Description | Fix |
|---|---|---|---|
| ZAPIT-2001 | Connecting | SSH connection attempt | Informational |
| ZAPIT-2002 | No Host Key | known_hosts not configured | ssh-keyscan -p 2222 IP >> known_hosts |
| ZAPIT-2003 | Key Mismatch | Server key changed | Remove old key, re-scan host |
| ZAPIT-2004 | Key Verified | Server identity confirmed | Informational |
| ZAPIT-2005 | Refused | Nothing on target port | systemctl start zapitd on receiver |
| ZAPIT-2006 | Timeout | Server unreachable | Check firewall: TCP port must be open |
| ZAPIT-2007 | Auth Rejected | Key not in authorized_keys | Add sender public key to receiver |
| ZAPIT-2008 | Connected | SSH established | Informational |
| ZAPIT-2009 | TOFU | Trust On First Use | Informational |
| ZAPIT-2010 | Insecure Mode | Host key verification disabled | Do not use in production |

### Handshake — ZAPIT-3xxx

| Code | Name | Description | Fix |
|---|---|---|---|
| ZAPIT-3001 | Handshake Sent | Initial message sent | Informational |
| ZAPIT-3002 | Accepted | Receiver ready | Informational |
| ZAPIT-3003 | Rejected | Receiver refused | Check receiver logs |
| ZAPIT-3004 | Metadata Sent | File structure sent | Informational |
| ZAPIT-3005 | Encryption Active | AES-256-GCM key exchanged | Informational |
| ZAPIT-3006 | No Encryption | Data sent unencrypted | Add encrypt: true to nodes.conf |

### Data Transfer — ZAPIT-4xxx

| Code | Name | Description | Fix |
|---|---|---|---|
| ZAPIT-4001 | Started | Sending chunks | Informational |
| ZAPIT-4002 | Chunk Acked | Received and written | Informational |
| ZAPIT-4003 | Chunk Nacked | Rejected, will retry | Automatic |
| ZAPIT-4004 | Chunk Retry | No ACK, retransmitting | Automatic |
| ZAPIT-4005 | Chunk Failed | All retries exhausted | Resume with zapit restart |
| ZAPIT-4006 | Window Reduced | Congestion detected | Automatic |
| ZAPIT-4007 | Window Increased | Network healthy | Informational |
| ZAPIT-4008 | Replay Started | Retrying failed chunks | Informational |
| ZAPIT-4009 | Replay Complete | All retries finished | Informational |
| ZAPIT-4010 | High Loss | Packet loss above 20% | Check network, reduce rate |
| ZAPIT-4011 | UDP Error | Data socket failed | Check UDP port open on receiver |
| ZAPIT-4012 | Pass 1 Complete | All chunks attempted | Informational |
| ZAPIT-4013 | FIN Sent | All chunks delivered | Informational |
| ZAPIT-4014 | Paused | Progress saved | Resume with zapit restart |

### Verification — ZAPIT-5xxx

| Code | Name | Description | Fix |
|---|---|---|---|
| ZAPIT-5001 | Requested | SHA-256 check started | Informational |
| ZAPIT-5002 | Passed | File is a perfect copy | No action |
| ZAPIT-5003 | Failed | Checksum mismatch | Delete destination, retransfer |
| ZAPIT-5004 | Incomplete | Channel closed before result | Manual sha256sum on both files |
| ZAPIT-5005 | Skipped | Default — AES-GCM verified per chunk | Normal |
| ZAPIT-5006 | Path Error | Cannot open destination for hash | Check permissions |

### Completion — ZAPIT-6xxx

| Code | Name | Description | Fix |
|---|---|---|---|
| ZAPIT-6001 | Completed | All chunks delivered | No action |
| ZAPIT-6002 | Failed | Transfer failed | Check error, fix, restart |
| ZAPIT-6003 | Manifest Updated | Final status written | Informational |
| ZAPIT-6004 | Chunks Only | Per-chunk verification | Manual sha256sum to confirm |
| ZAPIT-6005 | Summary | Final summary in log | Informational |

### Receiver — ZAPIT-7xxx

| Code | Name | Description | Fix |
|---|---|---|---|
| ZAPIT-7001 | Started | Daemon started | Informational |
| ZAPIT-7002 | Listening | Waiting for connections | Informational |
| ZAPIT-7003 | Connected | Sender authenticated | Informational |
| ZAPIT-7004 | Dir Not Found | Destination directory missing | mkdir -p directory |
| ZAPIT-7005 | Disk Full | No space left | Free space: df -h |
| ZAPIT-7006 | Cannot Create | Permission denied on output | Check directory permissions |
| ZAPIT-7008 | Sync Complete | Data flushed to disk | Informational |
| ZAPIT-7010 | Ready | Waiting for next connection | Informational |
| ZAPIT-7011 | Keys Empty | No senders registered | Add public key to authorized_keys |
| ZAPIT-7012 | No Host Key | Missing host key | ssh-keygen -t ed25519 -f host_key -N "" |

### System — ZAPIT-9xxx

| Code | Name | Description | Fix |
|---|---|---|---|
| ZAPIT-9001 | FIPS Disabled | Not built with FIPS | Use GOFIPS140=latest build |
| ZAPIT-9002 | FIPS Enabled | FIPS crypto active | Informational |
| ZAPIT-9003 | Log Created | New log session | Informational |
| ZAPIT-9004 | Manifest Dir | Cannot access manifest directory | mkdir -p $ZAPIT_HOME/manifest |
| ZAPIT-9005 | Shutdown | Service shutting down | Informational |

### File Commit — ZAPIT-10xxx

| Code | Name | Description | Fix |
|---|---|---|---|
| ZAPIT-10001 | Committed | Temp file renamed to final | Informational |
| ZAPIT-10002 | Source Deleted | Source removed after verified transfer | Informational |
| ZAPIT-10003 | Temp Created | Hidden temp file created | Informational |

### Cancel — ZAPIT-11xxx

| Code | Name | Description | Fix |
|---|---|---|---|
| ZAPIT-11001 | Cancelled | Cancel completed | Informational |
| ZAPIT-11002 | Refused (Complete) | Cannot cancel completed job | No action needed |
| ZAPIT-11003 | Refused (Already) | Job already cancelled | No action needed |

### Node Configuration — ZAPIT-12xxx

| Code | Name | Description | Fix |
|---|---|---|---|
| ZAPIT-12001 | Loaded | Configuration loaded | Informational |
| ZAPIT-12002 | Not Found | Node name not in nodes.conf | Check spelling: zapit nodes list |
| ZAPIT-12003 | Conf Missing | nodes.conf file missing | Create $ZAPIT_HOME/nodes/nodes.conf |

### Daemon — ZAPIT-13xxx

| Code | Name | Description | Fix |
|---|---|---|---|
| ZAPIT-13001 | Started | Daemon running | Informational |
| ZAPIT-13002 | Submitted | Job queued | Informational |
| ZAPIT-13003 | Job Started | Transfer running | Informational |
| ZAPIT-13004 | Held | Transfer paused | Informational |
| ZAPIT-13005 | Released | Transfer resumed | Informational |
| ZAPIT-13006 | Stopped | Transfer stopped gracefully | Informational |
| ZAPIT-13007 | Cancelled | Transfer cancelled | Informational |
| ZAPIT-13009 | Socket Ready | Unix socket accepting commands | Informational |

### Advanced — ZAPIT-14xxx

| Code | Name | Description | Fix |
|---|---|---|---|
| ZAPIT-14001 | ACK Received | RTT measurement active | Informational |
| ZAPIT-14002 | User Switched | Running as different OS user | Informational |
| ZAPIT-14003 | User Failed | Cannot switch user | Check zapit-reader setuid: chmod 4755 |
| ZAPIT-14004 | Purged | Old jobs removed | Informational |

---

## 22. Troubleshooting Guide

### 22.1 Connection Refused (ZAPIT-2005)

Cause: zapitd not running on receiver.

```
ssh user@receiver "sudo systemctl status zapitd"
ssh user@receiver "sudo systemctl start zapitd"
```

### 22.2 Connection Timeout (ZAPIT-2006)

Cause: firewall blocking TCP port.

```
nc -zv RECEIVER_IP 2222 -w 3
```

If fails: check firewall rules on both servers and network devices between them.

### 22.3 Authentication Rejected (ZAPIT-2007)

Cause: sender public key not in receiver authorized_keys.

```
cat $ZAPIT_HOME/security/transfer_key.pub
echo "PASTE_KEY" | sudo tee -a RECEIVER:$ZAPIT_HOME/security/authorized_keys
sudo systemctl restart zapitd  (on receiver)
```

### 22.4 Host Key Mismatch (ZAPIT-2003)

Cause: receiver host key changed (reinstall or key regeneration).

```
sudo rm -f $ZAPIT_HOME/security/known_hosts
ssh-keyscan -p 2222 RECEIVER_IP 2>/dev/null | sudo tee $ZAPIT_HOME/security/known_hosts
```

### 22.5 CLI Cannot Connect to Daemon

Cause: ZAPIT_HOME not set, socket missing, or old binary in PATH.

```
echo $ZAPIT_HOME
source /etc/profile.d/zapit.sh
which zapit
ls -la $ZAPIT_HOME/run/zapitd.sock
```

If which shows /usr/local/bin/zapit:

```
sudo rm -f /usr/local/bin/zapit* /usr/local/bin/zapitd
hash -r
```

### 22.6 Transfer Slow

```
sysctl net.core.rmem_max
```

Should show 268435456. If not:

```
sudo sysctl -p /etc/sysctl.d/99-zapit.conf
```

Check disk speed:

```
dd if=/dev/zero of=/tmp/disktest bs=1M count=1024 oflag=dsync
```

Try SPRINT+ Dedicated:

```
zapit submit --congestion sprint --target-rate 500m ...
```

If speed was previously 132 MB/s and now lower: likely EBS burst credits exhausted. Wait 30 minutes for recovery.

### 22.7 Disk Full (ZAPIT-7005)

```
df -h /data/received/
rm -f /data/received/old_files*
```

### 22.8 Source File Not Readable (ZAPIT-1003)

```
ls -la /path/to/source
```

If using --source-user:

```
ls -la $ZAPIT_HOME/bin/zapit-reader
sudo chown root:root $ZAPIT_HOME/bin/zapit-reader
sudo chmod 4755 $ZAPIT_HOME/bin/zapit-reader
```

### 22.9 Destination File Stuck as .zapit-tmp

```
grep "commit\|error\|FAIL" $ZAPIT_HOME/log/zapit-zapitd-$(date +%Y-%m-%d).log
```

Manual rename if data is complete:

```
mv /data/received/.filename.zapit-tmp /data/received/filename
```

### 22.10 Source File Modified During Transfer

Zapit checks source file stability before and after transfer. If the source file changes, the transfer fails. Wait for the source file to be completely written before submitting.

### 22.11 Daemon Fails to Start

```
journalctl -u zapitd --no-pager -n 20
```

Common causes: port in use (ss -tlnp | grep 2222), host key missing, manifest directory not writable, ZAPIT_HOME not set.

### 22.12 ZAPIT_HOME Not Set

```
source /etc/profile.d/zapit.sh
echo $ZAPIT_HOME
```

If /etc/sysconfig/zapit is missing:

```
echo "ZAPIT_HOME=/opt/zapit" | sudo tee /etc/sysconfig/zapit
```

### 22.13 Logs Not at Expected Path

Check which path the daemon uses:

```
ps aux | grep zapitd | grep -v grep
```

Find where today's log actually is:

```
sudo find / -name "zapit-zapitd-$(date +%Y-%m-%d).log" 2>/dev/null
```

### 22.14 Chunk Corrupted in Transit

AES-GCM auth tag failed — data was modified in transit. This triggers automatic retry. If persistent, check network equipment modifying UDP packets or contact network team.

---

## 23. RPM Package Management

| Command | Description |
|---|---|
| sudo rpm -ivh zapit-4.4.rpm | Fresh install |
| sudo rpm -Uvh zapit-4.5.rpm | Upgrade (preserves config) |
| sudo rpm -Uvh --oldpackage zapit-4.4.rpm | Rollback |
| sudo rpm -e zapit | Uninstall |
| rpm -q zapit | Check installed version |
| rpm -ql zapit | List installed files |
| rpm -qlp zapit-4.4.rpm | List files in RPM (before installing) |
| rpm -qi zapit | Package info |
| rpm -V zapit | Verify integrity |
| rpm -q --scripts -p zapit-4.4.rpm | View install/uninstall scripts |
| rpm --checksig zapit-4.4.rpm | Verify GPG signature |

---

## 24. FAQ

**Q: Can different servers name the same destination differently?**
A: Yes. Node names are local labels. Server A can call it "PROD_B" while Server C calls it "PROD_BB". Both connect to the same receiver.

**Q: Does zapit lock the source file during transfer?**
A: No. Zapit performs a stability check (stat before and after) but does not hold a file lock. Ensure the source file is fully written before submitting.

**Q: What happens if the network drops during transfer?**
A: The transfer fails. The manifest preserves progress. Run zapit restart --id JOB_ID to resume from where it stopped.

**Q: Can I transfer to multiple servers simultaneously?**
A: Yes. Submit multiple jobs to different nodes. There is no limit on concurrent transfers.

**Q: Does the same RPM install on both sender and receiver?**
A: Yes. Same RPM on every server. zapitd handles both sending and receiving.

**Q: Does encryption slow down transfers?**
A: No. AES-256-GCM with hardware AES-NI provides ~3,000 MB/s encryption throughput. Disk I/O is always the bottleneck, not encryption.

**Q: What is the maximum file size?**
A: No hard limit. Tested with 15 GB. Designed to handle files exceeding 1 TB.

**Q: Does GOFIPS140 slow transfers?**
A: No. FIPS adds approximately 8ms at daemon startup and 1ms per transfer. Encryption uses the same AES-NI hardware instructions.

---

## 25. Appendix A — verify.sh Script

```bash
#!/bin/bash
echo ""
echo "  ZAPIT INSTALLATION VERIFICATION"
echo "  Server: $(hostname)"
echo "  Date:   $(date)"
echo ""

if [ -z "$ZAPIT_HOME" ]; then
    echo "  ERROR: ZAPIT_HOME is not set"
    echo "  Run: source /etc/profile.d/zapit.sh"
    exit 1
fi

echo "  ZAPIT_HOME = $ZAPIT_HOME"
echo ""

PASS=0; FAIL=0

check() {
    if [ $1 -eq 0 ]; then
        echo "  PASS  $2"; PASS=$((PASS + 1))
    else
        echo "  FAIL  $2"; FAIL=$((FAIL + 1))
    fi
}

echo "  --- Directories and Files ---"
test -d "$ZAPIT_HOME/bin" && ls "$ZAPIT_HOME/bin/zapitd" >/dev/null 2>&1
check $? "Binaries at $ZAPIT_HOME/bin/"
test -d "$ZAPIT_HOME/nodes"; check $? "Nodes dir"
test -f "$ZAPIT_HOME/nodes/nodes.conf"; check $? "nodes.conf"
test -d "$ZAPIT_HOME/log"; check $? "Log dir"
test -d "$ZAPIT_HOME/manifest"; check $? "Manifest dir"
test -d "$ZAPIT_HOME/security"; check $? "Security dir"
test -f "$ZAPIT_HOME/security/host_key"; check $? "Host key"
test -f "$ZAPIT_HOME/security/authorized_keys"; check $? "Authorized keys"
test -d "$ZAPIT_HOME/run"; check $? "Run dir"
test -S "$ZAPIT_HOME/run/zapitd.sock"; check $? "Socket"
test -f "/etc/sysconfig/zapit"; check $? "Env file"

echo ""
echo "  --- Old Paths (should NOT exist) ---"
test ! -f "/var/log/zapit/zapit-zapitd-$(date +%Y-%m-%d).log"
check $? "No old log at /var/log/zapit/"
test ! -S "/var/run/zapit/zapitd.sock" 2>/dev/null
check $? "No old socket at /var/run/zapit/"
test ! -f "/usr/local/bin/zapitd"
check $? "No old binary at /usr/local/bin/"

echo ""
echo "  --- Service ---"
systemctl is-active zapitd >/dev/null 2>&1; check $? "Daemon running"
ps aux | grep "[z]apitd" | grep -q "$ZAPIT_HOME/bin/zapitd"
check $? "Using binary from $ZAPIT_HOME/bin/"

echo ""
echo "  RESULT: $PASS passed, $FAIL failed"
if [ $FAIL -eq 0 ]; then
    echo "  ALL CHECKS PASSED"
else
    echo "  $FAIL CHECKS FAILED"
fi
echo ""
```

---

## 26. Appendix B — Sample nodes.conf

```
nodes:
  PRODUCTION_SERVER_B:
    host:            10.0.1.50
    port:            2222
    udp_port:        9000
    encrypt:         true
    key:             /opt/zapit/security/transfer_key
    known_hosts:     /opt/zapit/security/known_hosts
    connect_timeout: 10
    chunk_mib:       1
    max_retries:     5
    window:          64
    max_window:      512
    rate_mbps:       0
    description:     Production Server B

  DR_SITE:
    host:            10.0.2.100
    port:            2222
    udp_port:        9000
    encrypt:         true
    key:             /opt/zapit/security/dr_key
    known_hosts:     /opt/zapit/security/known_hosts
    connect_timeout: 30
    chunk_mib:       1
    max_retries:     10
    window:          64
    max_window:      512
    rate_mbps:       0
    description:     Disaster Recovery Site
```

---

## 27. Appendix C — Firewall Rules

### AWS Security Group

```
Inbound on receiver:
  Custom TCP   Port 2222   Source: sender-security-group
  Custom UDP   Port 9000   Source: sender-security-group
```

### iptables

```
sudo iptables -A INPUT -p tcp --dport 2222 -s SENDER_IP -j ACCEPT
sudo iptables -A INPUT -p udp --dport 9000 -s SENDER_IP -j ACCEPT
```

### firewalld

```
sudo firewall-cmd --permanent --add-rich-rule='rule family="ipv4" source address="SENDER_IP" port port="2222" protocol="tcp" accept'
sudo firewall-cmd --permanent --add-rich-rule='rule family="ipv4" source address="SENDER_IP" port port="9000" protocol="udp" accept'
sudo firewall-cmd --reload
```

---

## 28. Appendix D — Quick Reference Card

```
INSTALL:     sudo rpm -ivh zapit-4.4-1.x86_64.rpm
UPGRADE:     sudo rpm -Uvh zapit-4.5-1.x86_64.rpm
UNINSTALL:   sudo rpm -e zapit
ENV:         source /etc/profile.d/zapit.sh
STATUS:      systemctl status zapitd
START:       sudo systemctl start zapitd
STOP:        sudo systemctl stop zapitd
RESTART:     sudo systemctl restart zapitd

SUBMIT:      zapit submit --src FILE --dest FILE --node NAME --remote-user USER
LIST:        zapit list
CANCEL:      zapit cancel --id JOB_ID
RESTART:     zapit restart --id JOB_ID
HOLD:        zapit hold --id JOB_ID
RELEASE:     zapit release --id JOB_ID
PURGE:       zapit purge
NODES:       zapit nodes list
HEARTBEAT:   zapit nodes test --node NAME

LOGS:        tail -f $ZAPIT_HOME/log/zapit-zapitd-$(date +%Y-%m-%d).log
ERRORS:      grep "level=ERROR" $ZAPIT_HOME/log/zapit-zapitd-$(date +%Y-%m-%d).log
RESULTS:     grep "avg_rate\|COMPLETE\|FAILED" $ZAPIT_HOME/log/zapit-zapitd-$(date +%Y-%m-%d).log
VERIFY:      bash verify.sh
```

---

*End of Document*
