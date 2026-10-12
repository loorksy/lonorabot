import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { lingui } from "@lingui/vite-plugin";
export default defineConfig({plugins:[react({babel:{plugins:["@lingui/babel-plugin-lingui-macro"]}}),tailwindcss(),lingui()],server:{proxy:{"/api":{target:"http://127.0.0.1:8000",ws:true},"/health":"http://127.0.0.1:8000","/ready":"http://127.0.0.1:8000"}},build:{outDir:"dist"}});
