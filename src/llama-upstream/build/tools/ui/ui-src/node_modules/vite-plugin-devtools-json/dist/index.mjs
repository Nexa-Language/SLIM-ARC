import fs from 'fs';
import path from 'path';
import { validate, v4 } from 'uuid';

const ENDPOINT = "/.well-known/appspecific/com.chrome.devtools.json";
const plugin = (options) => ({
  name: "devtools-json",
  enforce: "post",
  configureServer(server) {
    const { config } = server;
    const { logger } = config;
    if (!config.env.DEV) {
      return;
    }
    const getOrCreateUUID = () => {
      if (options?.uuid) {
        return options.uuid;
      }
      let { cacheDir } = config;
      if (!path.isAbsolute(cacheDir)) {
        let { root } = config;
        if (!path.isAbsolute(root)) {
          root = path.resolve(process.cwd(), root);
        }
        cacheDir = path.resolve(root, cacheDir);
      }
      const uuidPath = path.resolve(cacheDir, "uuid.json");
      if (fs.existsSync(uuidPath)) {
        const uuid2 = fs.readFileSync(uuidPath, { encoding: "utf-8" });
        if (validate(uuid2)) {
          return uuid2;
        }
      }
      if (!fs.existsSync(cacheDir)) {
        fs.mkdirSync(cacheDir, { recursive: true });
      }
      const uuid = v4();
      fs.writeFileSync(uuidPath, uuid, { encoding: "utf-8" });
      logger.info(`Generated UUID '${uuid}' for DevTools project settings.`);
      return uuid;
    };
    server.middlewares.use(ENDPOINT, async (req, res) => {
      let { root } = config;
      if (!path.isAbsolute(root)) {
        root = path.resolve(process.cwd(), root);
      }
      if (process.env.WSL_DISTRO_NAME) {
        root = path.join("\\\\wsl.localhost", process.env.WSL_DISTRO_NAME, root).replace(/\//g, "\\");
      }
      const uuid = getOrCreateUUID();
      const devtoolsJson = {
        workspace: {
          root,
          uuid
        }
      };
      res.setHeader("Content-Type", "application/json");
      res.end(JSON.stringify(devtoolsJson, null, 2));
    });
  }
});

export { plugin as default };
