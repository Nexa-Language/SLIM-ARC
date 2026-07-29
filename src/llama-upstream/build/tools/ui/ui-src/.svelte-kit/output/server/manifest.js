export const manifest = (() => {
function __memo(fn) {
	let value;
	return () => value ??= (value = fn());
}

return {
	appDir: "_app",
	appPath: "_app",
	assets: new Set(["apple-splash-landscape-1136x640.png","apple-splash-landscape-1334x750.png","apple-splash-landscape-2266x1488.png","apple-splash-landscape-2360x1640.png","apple-splash-landscape-2388x1668.png","apple-splash-landscape-2532x1170.png","apple-splash-landscape-2556x1179.png","apple-splash-landscape-2622x1206.png","apple-splash-landscape-2732x2048.png","apple-splash-landscape-2778x1284.png","apple-splash-landscape-2796x1290.png","apple-splash-landscape-2868x1320.png","apple-splash-landscape-dark-1136x640.png","apple-splash-landscape-dark-1334x750.png","apple-splash-landscape-dark-2266x1488.png","apple-splash-landscape-dark-2360x1640.png","apple-splash-landscape-dark-2388x1668.png","apple-splash-landscape-dark-2532x1170.png","apple-splash-landscape-dark-2556x1179.png","apple-splash-landscape-dark-2622x1206.png","apple-splash-landscape-dark-2732x2048.png","apple-splash-landscape-dark-2778x1284.png","apple-splash-landscape-dark-2796x1290.png","apple-splash-landscape-dark-2868x1320.png","apple-splash-portrait-1170x2532.png","apple-splash-portrait-1179x2556.png","apple-splash-portrait-1206x2622.png","apple-splash-portrait-1284x2778.png","apple-splash-portrait-1290x2796.png","apple-splash-portrait-1320x2868.png","apple-splash-portrait-1488x2266.png","apple-splash-portrait-1640x2360.png","apple-splash-portrait-1668x2388.png","apple-splash-portrait-2048x2732.png","apple-splash-portrait-640x1136.png","apple-splash-portrait-750x1334.png","apple-splash-portrait-dark-1170x2532.png","apple-splash-portrait-dark-1179x2556.png","apple-splash-portrait-dark-1206x2622.png","apple-splash-portrait-dark-1284x2778.png","apple-splash-portrait-dark-1290x2796.png","apple-splash-portrait-dark-1320x2868.png","apple-splash-portrait-dark-1488x2266.png","apple-splash-portrait-dark-1640x2360.png","apple-splash-portrait-dark-1668x2388.png","apple-splash-portrait-dark-2048x2732.png","apple-splash-portrait-dark-640x1136.png","apple-splash-portrait-dark-750x1334.png","apple-touch-icon-180x180.png","favicon-dark.ico","favicon-dark.svg","favicon.ico","favicon.svg","loading.html","maskable-icon-512x512.png","pwa-192x192.png","pwa-512x512.png","pwa-64x64.png"]),
	mimeTypes: {".png":"image/png",".svg":"image/svg+xml",".html":"text/html"},
	_: {
		client: {start:"_app/immutable/bundle.Gy95mi7G.js",imports:["_app/immutable/bundle.Gy95mi7G.js"],stylesheets:["_app/immutable/assets/bundle.B-5zNnG1.css"],fonts:[],uses_env_dynamic_public:false},
		nodes: [
			__memo(() => import('./nodes/0.js')),
			__memo(() => import('./nodes/1.js')),
			__memo(() => import('./nodes/2.js')),
			__memo(() => import('./nodes/3.js')),
			__memo(() => import('./nodes/4.js')),
			__memo(() => import('./nodes/5.js')),
			__memo(() => import('./nodes/6.js')),
			__memo(() => import('./nodes/7.js'))
		],
		remotes: {
			
		},
		routes: [
			{
				id: "/(chat)",
				pattern: /^\/?$/,
				params: [],
				page: { layouts: [0,2,], errors: [1,,], leaf: 4 },
				endpoint: null
			},
			{
				id: "/(chat)/chat/[id]",
				pattern: /^\/chat\/([^/]+?)\/?$/,
				params: [{"name":"id","optional":false,"rest":false,"chained":false}],
				page: { layouts: [0,2,], errors: [1,,], leaf: 5 },
				endpoint: null
			},
			{
				id: "/mcp-servers",
				pattern: /^\/mcp-servers\/?$/,
				params: [],
				page: { layouts: [0,], errors: [1,], leaf: 6 },
				endpoint: null
			},
			{
				id: "/settings/[[section]]",
				pattern: /^\/settings(?:\/([^/]+))?\/?$/,
				params: [{"name":"section","optional":true,"rest":false,"chained":true}],
				page: { layouts: [0,3,], errors: [1,,], leaf: 7 },
				endpoint: null
			}
		],
		prerendered_routes: new Set([]),
		matchers: async () => {
			
			return {  };
		},
		server_assets: {}
	}
}
})();
