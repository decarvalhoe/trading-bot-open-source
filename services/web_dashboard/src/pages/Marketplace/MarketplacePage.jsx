import React from "react";
import MarketplaceApp from "../../marketplace/MarketplaceApp.jsx";
import { bootstrap } from "../../bootstrap";

export default function MarketplacePage() {
  const config = bootstrap?.config?.marketplace || {};
  const marketplaceData = bootstrap?.data?.marketplace || {};
  const listingsEndpoint = marketplaceData.listingsEndpoint || config.listingsEndpoint || "/marketplace/listings";
  const reviewsEndpointTemplate =
    marketplaceData.reviewsEndpointTemplate || config.reviewsEndpointTemplate || "/marketplace/listings/__id__/reviews";

  return (
    <MarketplaceApp listingsEndpoint={listingsEndpoint} reviewsEndpointTemplate={reviewsEndpointTemplate} />
  );
}
