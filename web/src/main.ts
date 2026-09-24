import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import { router } from './router'
import { t } from './i18n'
import './assets/styles.css'
import './assets/dialog.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.config.globalProperties.$t = t
app.mount('#app')
