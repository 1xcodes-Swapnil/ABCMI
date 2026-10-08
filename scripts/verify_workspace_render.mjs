// Render every production tab with the saved real meeting; no API stubs or inference.
// This checks React rendering only and deliberately does not claim browser interaction.
import {build} from 'esbuild';
import React from 'react';
import {renderToString} from 'react-dom/server';
import Module from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
const bundled = await build({stdin:{contents:"export {default as App} from './src/App'; export {WorkspacePanels} from './src/components/WorkspacePanels';", resolveDir:process.cwd(), loader:'tsx'},bundle:true, platform:'node', format:'cjs',write:false,external:['react','react-dom','react/jsx-runtime']});
const mod = new Module(path.resolve('workspace-render.cjs'));
mod.filename = path.resolve('workspace-render.cjs');
mod.paths = Module._nodeModulePaths(process.cwd());
mod._compile(bundled.outputFiles[0].text,mod.filename);
const record = JSON.parse(fs.readFileSync('e2e_validation/runs/workspace_20261003T071701Z/response_02.json','utf8'));
const me = JSON.parse(fs.readFileSync('e2e_validation/runs/workspace_20261003T071701Z/response_00.json','utf8'));
const tabs = ['meetings','live_stream','intelligence','queries','knowledge','translations','reports','benchmarks','security','api_console','system_health'];
const result = {timestamp:new Date().toISOString(),browser_interaction:'NOT VERIFIED',audio_inference_executed:false,tabs:[]};
const initial = renderToString(React.createElement(mod.exports.App));
if (!initial.includes('Connect your workspace')) throw new Error('Unauthenticated connection screen missing');
for (const tab of tabs) {
  const html = renderToString(React.createElement(mod.exports.WorkspacePanels,{tab,meetings:[record],meetingId:record.id,select:()=>{},refresh:async()=>{},navigate:()=>{},auth:{...me,token:'',tenant_id:me.tenant_id}}));
  if (!html.length || html.includes('jwt-hs256-mock-token-sample')) throw new Error(`Invalid production rendering: ${tab}`);
  result.tabs.push({tab,rendered:true,html_bytes:Buffer.byteLength(html)});
}
const destination = `e2e_validation/diagnostics/workspace-render-${Date.now()}.json`;
fs.writeFileSync(destination,JSON.stringify(result,null,2),{flag:'wx'});
console.log(JSON.stringify({tabs_rendered:result.tabs.length,unauthenticated_screen:true,browser_interaction:result.browser_interaction,evidence:destination}));
