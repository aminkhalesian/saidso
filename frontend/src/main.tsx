import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import "./index.css";
import { AppProvider, useApp } from "./context";
import { Shell } from "./components/Shell";
import { MyWeek } from "./pages/MyWeek";
import { Renewals } from "./pages/Renewals";
import { Account } from "./pages/Account";
import { Portfolio } from "./pages/Portfolio";
import { Trust } from "./pages/Trust";
import { Analyze } from "./pages/Analyze";
import { Loading } from "./components/ui";

function Home() {
  const { clients } = useApp();
  if (!clients.length) return <Loading label="Connecting to the backend" />;
  return <Navigate to={`/${clients[0].id}/week`} replace />;
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AppProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/:clientId" element={<Shell />}>
            <Route index element={<Navigate to="week" replace />} />
            <Route path="week" element={<MyWeek />} />
            <Route path="renewals" element={<Renewals />} />
            <Route path="accounts/:accountId" element={<Account />} />
            <Route path="portfolio" element={<Portfolio />} />
            <Route path="trust" element={<Trust />} />
            <Route path="analyze" element={<Analyze />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AppProvider>
  </React.StrictMode>,
);
