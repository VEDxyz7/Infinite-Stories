// Offline tooling guard, never an application/provider mock. All attempted
// network or process execution fails; no simulated response is returned.
import { syncBuiltinESMExports } from 'node:module';
import http from 'node:http';
import https from 'node:https';
import net from 'node:net';
import tls from 'node:tls';
import dns from 'node:dns';
import childProcess from 'node:child_process';
let attempts = 0;
function blocked() { attempts++; throw new Error('OFFLINE_GUARD_NETWORK_OR_PROCESS_DENIED'); }
globalThis.fetch = blocked;
for (const module of [http, https]) { module.request = blocked; module.get = blocked; }
net.connect = blocked; net.createConnection = blocked;
net.Socket.prototype.connect = blocked;
tls.connect = blocked;
dns.lookup = blocked; dns.resolve = blocked;
for (const key of ['spawn', 'spawnSync', 'exec', 'execSync', 'execFile', 'execFileSync', 'fork']) childProcess[key] = blocked;
syncBuiltinESMExports();
process.on('exit', () => process.stderr.write(`OFFLINE_GUARD_ATTEMPTS=${attempts}\n`));
