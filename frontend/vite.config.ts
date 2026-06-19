import { dirname, resolve } from "path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import Icons from "unplugin-icons/vite";
import IconsResolver from "unplugin-icons/resolver";
import Components from "unplugin-vue-components/vite";
import { ElementPlusResolver } from "unplugin-vue-components/resolvers";
import AutoImport from "unplugin-auto-import/vite";

const __viteConfigDir = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  base: "/web/",
  plugins: [
    vue(),
    AutoImport({
      resolvers: [ElementPlusResolver()],
      imports: ["vue", "vue-router", "pinia"],
      dts: true,
      eslintrc: {
        enabled: true,
      },
    }),
    Components({
      resolvers: [
        ElementPlusResolver({
          importStyle: false,
        }),
        IconsResolver({
          prefix: "i",
          enabledCollections: ["ion", "mdi"],
        }),
      ],
    }),
    Icons({
      compiler: "vue3",
      autoInstall: true,
    }),
  ],
  resolve: {
    alias: {
      "@": resolve(__viteConfigDir, "src"),
    },
  },
  optimizeDeps: {
    include: ["element-plus", "element-plus/es"],
  },
  server: {
    host: "localhost",
    port: 5174,
    proxy: {
      "/v_factory": {
        target: "http://localhost:9002",
        changeOrigin: true,
      },
      "/health": {
        target: "http://localhost:9002",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    assetsDir: "assets",
    chunkSizeWarningLimit: 1000,
    rollupOptions: {
      preserveEntrySignatures: false,
      output: {
        assetFileNames: assetInfo => {
          const info = assetInfo.name?.split(".") || [];
          const ext = info[info.length - 1];
          if (/\.(png|jpe?g|gif|svg|webp|ico)$/.test(assetInfo.name || "")) {
            return "assets/images/[name]-[hash:8].[ext]";
          }
          if (ext === "css") {
            return "assets/css/[name]-[hash:8].[ext]";
          }
          return "assets/[name]-[hash:8].[ext]";
        },
        chunkFileNames: "assets/js/[name]-[hash:8].js",
        entryFileNames: "assets/js/[name]-[hash:8].js",
        manualChunks(id) {
          if (id.includes("node_modules")) {
            if (
              id.includes("node_modules/vue/") ||
              id.includes("node_modules/vue-router/") ||
              id.includes("node_modules/pinia/") ||
              id.includes("node_modules/@vue/")
            ) {
              return "vue-vendor";
            }
            if (
              id.includes("node_modules/element-plus/") ||
              id.includes("node_modules/@element-plus/")
            ) {
              return "element-plus";
            }
            if (
              id.includes("node_modules/axios/") ||
              id.includes("node_modules/lodash-es/") ||
              id.includes("node_modules/dayjs/")
            ) {
              return "utils";
            }
            if (id.includes("node_modules/vant/")) {
              return "vant";
            }
            return "vendor";
          }

          if (
            (id.includes("/api/") ||
              id.includes("/types/") ||
              id.includes("/utils/") ||
              id.includes("/constants/")) &&
            !id.includes("/views/") &&
            !id.includes("node_modules")
          ) {
            return "shared";
          }
        },
      },
    },
  },
});
