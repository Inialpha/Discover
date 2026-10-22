import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { Analytics } from "@vercel/analytics/react";
import "@fontsource-variable/bricolage-grotesque";
import "@fontsource-variable/figtree";
import "./styles.css";
import App from "./App";
import { AuthProvider } from "./auth";

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
      <Analytics />  {/* Vercel Web Analytics: page views only; it does nothing until enabled in the Vercel dashboard */}
    </BrowserRouter>
  </React.StrictMode>,
);
