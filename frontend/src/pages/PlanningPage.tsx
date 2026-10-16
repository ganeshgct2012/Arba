import { ProductListing } from "./ProductListing";
import { PromoCalendar } from "./PromoCalendar";
import { Promotions } from "./Promotions";
import { SalesHistory } from "./SalesHistory";
import { VolumeReport } from "./VolumeReport";
import { WeeklyVolume } from "./WeeklyVolume";
import { type PageProps } from "../types";

export function PlanningPage(props: PageProps) {
  switch (props.page) {
    case "weekly": return <WeeklyVolume {...props} />;
    case "promotions": return <Promotions {...props} />;
    case "calendar": return <PromoCalendar {...props} />;
    case "history": return <SalesHistory {...props} />;
    case "report": return <VolumeReport {...props} />;
    case "listing": return <ProductListing {...props} />;
    default: return null;
  }
}

