"use client";

import type { UserEntitlement } from "../lib/api";

export function EntitlementBadge({ entitlement }: { entitlement: UserEntitlement | null }) {
  if (!entitlement) return <span className="entitlement-badge entitlement-badge--none">未购买</span>;
  if (entitlement.status === "expired") {
    return <span className="entitlement-badge entitlement-badge--expired">已过期</span>;
  }
  if (entitlement.access_type === "free") {
    return <span className="entitlement-badge entitlement-badge--free">免费</span>;
  }
  if (entitlement.access_type === "onetime") {
    return <span className="entitlement-badge entitlement-badge--owned">永久</span>;
  }
  return <span className="entitlement-badge entitlement-badge--owned">订阅中</span>;
}
