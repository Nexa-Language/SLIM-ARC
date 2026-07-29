import{r as a}from"./root.js";import"./environment.js";import"./server.js";let s=null;function h(t){s=t}function f(t){}let o={};function g(t){}function u(t){o=t}const v={app_template_contains_nonce:!1,async:!1,csp:{mode:"auto",directives:{"upgrade-insecure-requests":!1,"block-all-mixed-content":!1},reportOnly:{"upgrade-insecure-requests":!1,"block-all-mixed-content":!1}},csrf_check_origin:!0,csrf_trusted_origins:[],embedded:!1,env_public_prefix:"PUBLIC_",env_private_prefix:"",hash_routing:!0,hooks:null,preload_strategy:"modulepreload",root:a,service_worker:!1,service_worker_options:void 0,server_error_boundaries:!1,templates:{app:({head:t,body:n,assets:e,nonce:i,env:r})=>`<!doctype html>
<html lang="en">
	<head>
		<meta charset="utf-8" />
		<link rel="icon" href="favicon.ico" sizes="48x48" />
		<link rel="icon" href="favicon.svg" sizes="any" type="image/svg+xml" />

		<link rel="apple-touch-icon" href="apple-touch-icon-180x180.png" />

		<link rel="manifest" href="./manifest.webmanifest" />

		<meta
			name="viewport"
			content="width=device-width, initial-scale=1, interactive-widget=resizes-content"
		/>
		`+t+`
	</head>

	<body data-sveltekit-preload-data="hover">
		<div style="display: contents">`+n+`</div>
	</body>
</html>
`,error:({status:t,message:n})=>`<!doctype html>
<html lang="en">
	<head>
		<meta charset="utf-8" />
		<title>`+n+`</title>

		<style>
			body {
				--bg: white;
				--fg: #222;
				--divider: #ccc;
				background: var(--bg);
				color: var(--fg);
				font-family:
					system-ui,
					-apple-system,
					BlinkMacSystemFont,
					'Segoe UI',
					Roboto,
					Oxygen,
					Ubuntu,
					Cantarell,
					'Open Sans',
					'Helvetica Neue',
					sans-serif;
				display: flex;
				align-items: center;
				justify-content: center;
				height: 100vh;
				margin: 0;
			}

			.error {
				display: flex;
				align-items: center;
				max-width: 32rem;
				margin: 0 1rem;
			}

			.status {
				font-weight: 200;
				font-size: 3rem;
				line-height: 1;
				position: relative;
				top: -0.05rem;
			}

			.message {
				border-left: 1px solid var(--divider);
				padding: 0 0 0 1rem;
				margin: 0 0 0 1rem;
				min-height: 2.5rem;
				display: flex;
				align-items: center;
			}

			.message h1 {
				font-weight: 400;
				font-size: 1em;
				margin: 0;
			}

			@media (prefers-color-scheme: dark) {
				body {
					--bg: #222;
					--fg: #ddd;
					--divider: #666;
				}
			}
		</style>
	</head>
	<body>
		<div class="error">
			<span class="status">`+t+`</span>
			<div class="message">
				<h1>`+n+`</h1>
			</div>
		</div>
	</body>
</html>
`},version_hash:"pn1sdv"};async function _(){return{handle:void 0,handleFetch:void 0,handleError:void 0,handleValidationError:void 0,init:void 0,reroute:void 0,transport:void 0}}export{u as a,h as b,f as c,_ as g,v as o,o as p,s as r,g as s};
