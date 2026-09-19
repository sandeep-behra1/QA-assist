import { Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Configuration } from "./pages/Configuration";
import { Dashboard } from "./pages/Dashboard";
import { LeadCreate } from "./pages/LeadCreate";
import { LeadDetail } from "./pages/LeadDetail";
import { Leads } from "./pages/Leads";
import { QAReview } from "./pages/QAReview";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="leads" element={<Leads />} />
        <Route path="leads/new" element={<LeadCreate />} />
        <Route path="leads/:leadId" element={<LeadDetail />} />
        <Route path="review" element={<QAReview />} />
        <Route path="configuration" element={<Configuration />} />
      </Route>
    </Routes>
  );
}
