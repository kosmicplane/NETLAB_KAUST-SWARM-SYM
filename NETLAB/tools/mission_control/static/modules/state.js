export const state={page:'overview',status:{},telemetry:{},config:{},jobs:[],sync:{},listeners:new Set()};
export function setState(patch){Object.assign(state,patch);for(const fn of state.listeners)fn(state)}
export function subscribe(fn){state.listeners.add(fn);return()=>state.listeners.delete(fn)}
