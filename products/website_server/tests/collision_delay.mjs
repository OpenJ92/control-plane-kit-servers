// Keep the owned child alive while an already-bound foreign listener responds.
await new Promise(resolve => setTimeout(resolve,3000));
await import('./original-main.mjs');
