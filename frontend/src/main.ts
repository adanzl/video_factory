import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import router from "./router";
import "element-plus/dist/index.css";
import Vant from "vant";
import "vant/lib/index.css";
import "@vant/touch-emulator";
import "./styles/main.css";
import { ElMessage, ElMessageBox } from "element-plus";

const app = createApp(App);
const pinia = createPinia();

app.use(pinia);
app.use(router);
app.use(Vant);

app.config.globalProperties.$message = ElMessage;
app.config.globalProperties.$msgbox = ElMessageBox;

app.mount("#app");
