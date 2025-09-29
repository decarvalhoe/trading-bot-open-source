# Reports Service

The reports service exposes analytics endpoints for trading strategies and now supports on-demand PDF rendering for distribution.

## PDF rendering

The `/reports/{symbol}/render` endpoint renders one of the available report templates (symbol overview, daily risk summary, or portfolio performance) and converts it to a PDF file.

```http
POST /reports/AAPL/render
Content-Type: application/json

{
  "report_type": "symbol",
  "timeframe": "both"
}
```

### Request body

| Field | Type | Description |
| --- | --- | --- |
| `report_type` | `"symbol" \| "daily" \| "performance"` | Selects the template to render. Defaults to `"symbol"`. |
| `timeframe` | `"daily" \| "intraday" \| "both"` | Restricts symbol reports to a timeframe. Ignored for other types. |
| `account` | `string` | Optional account filter for aggregated reports. |
| `limit` | `integer` | Optional cap (1-365) on the number of rows in daily risk reports. |

### Response

The endpoint returns an `application/pdf` response and stores the generated document on disk. The absolute path is returned in the `X-Report-Path` header and the filename is included in the `Content-Disposition` header. Configure the output directory with the `REPORTS_STORAGE_PATH` environment variable (defaults to `./generated-reports`).

Templates are located in [`services/reports/app/templates`](app/templates) and use Jinja2 for formatting.
