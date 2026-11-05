// Test-only HTTPS adapter. The actual Web main and serving code still run.
// No network upstream or real credential is used.
import https from 'node:https';
import {EventEmitter} from 'node:events';
import {PassThrough} from 'node:stream';
import {writeFileSync} from 'node:fs';
https.request = (_url, _options, callback) => {
  const outgoing = new EventEmitter();
  let timer;
  outgoing.end = () => {
    writeFileSync('/run/witness/admitted', 'yes');
    timer = setTimeout(() => {
      const response = new PassThrough();
      response.statusCode = 200;
      response.headers = {'content-type':'application/json'};
      callback(response);
      response.end('{"recorded":true}');
    }, 9000);
  };
  outgoing.destroy = () => { clearTimeout(timer); };
  return outgoing;
};
await import('./original-main.mjs');
