const i=!1;function o(e){throw new Error("https://svelte.dev/e/experimental_async_required")}function l(e){throw new Error("https://svelte.dev/e/lifecycle_outside_component")}function s(){const e=new Error(`await_invalid
Encountered asynchronous work while rendering synchronously.
https://svelte.dev/e/await_invalid`);throw e.name="Svelte error",e}function c(e){const n=new Error(`dynamic_element_invalid_tag
\`<svelte:element this="${e}">\` is not a valid element name — the element will not be rendered
https://svelte.dev/e/dynamic_element_invalid_tag`);throw n.name="Svelte error",n}function d(e,n){const r=new Error(`hydratable_serialization_failed
Failed to serialize \`hydratable\` data for key \`${e}\`.

\`hydratable\` can serialize anything [\`uneval\` from \`devalue\`](https://npmjs.com/package/uneval) can, plus Promises.

Cause:
${n}
https://svelte.dev/e/hydratable_serialization_failed`);throw r.name="Svelte error",r}function v(){const e=new Error("invalid_csp\n`csp.nonce` was set while `csp.hash` was `true`. These options cannot be used simultaneously.\nhttps://svelte.dev/e/invalid_csp");throw e.name="Svelte error",e}function _(){const e=new Error("invalid_id_prefix\nThe `idPrefix` option cannot include `--`.\nhttps://svelte.dev/e/invalid_id_prefix");throw e.name="Svelte error",e}function u(e){const n=new Error(`lifecycle_function_unavailable
\`${e}(...)\` is not available on the server
https://svelte.dev/e/lifecycle_function_unavailable`);throw n.name="Svelte error",n}function t(){const e=new Error("server_context_required\nCould not resolve `render` context.\nhttps://svelte.dev/e/server_context_required");throw e.name="Svelte error",e}function h(){const e=a?.getStore();return t(),e}let a=null;export{l as a,i as b,s as c,c as d,o as e,v as f,h as g,d as h,_ as i,u as l};
