import { Heading } from "../../components/Heading";
import { configNames } from "../../constants";
import { AccessManagement } from "./AccessManagement";
import { BatchConfiguration } from "./BatchConfiguration";
import { FilesConfiguration } from "./FilesConfiguration";
import { MasterDataConfig } from "./MasterDataConfig";
import { type Bootstrap, type ConfigTab } from "../../types";

export function Configuration(props: {
  activeTab: ConfigTab;
  setActiveTab: (tab: ConfigTab) => void;
  isSystemAdmin: boolean;
  bootstrap: Bootstrap;
  flash: (message: string) => void;
  setError: (message: string) => void;
  refresh: () => void;
}) {
  const tabs: ConfigTab[] = props.isSystemAdmin
    ? ["access", "customer", "product", "batch", "files"]
    : ["access"];
  return <>
    <Heading title="Configuration" subtitle="Control access, master data, pipeline schedules, and integration files" />
    <nav className="config-tabs" aria-label="Configuration sections">
      {tabs.map((tab) => <button
        aria-current={props.activeTab === tab ? "page" : undefined}
        className={`button ${props.activeTab === tab ? "tab-active" : ""}`}
        key={tab}
        onClick={() => props.setActiveTab(tab)}
      >{configNames[tab]}</button>)}
    </nav>
    {props.activeTab === "access" && <AccessManagement {...props} />}
    {(props.activeTab === "customer" || props.activeTab === "product") &&
      <MasterDataConfig {...props} type={props.activeTab} />}
    {props.activeTab === "batch" && <BatchConfiguration {...props} />}
    {props.activeTab === "files" && <FilesConfiguration {...props} />}
  </>;
}

