import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ReportsList from "./ReportsList.jsx";

const sampleReports = [
  {
    id: "1",
    report_type: "Rapport quotidien",
    period: "01/01/2024 → 05/01/2024",
    generated_at: "2024-01-05T10:00:00Z",
    download_url: "http://example.com/report1.pdf",
  },
  {
    id: "2",
    report_type: "Rapport hebdomadaire",
    period: "Semaine 05",
    generated_at: "2024-02-02T12:45:00Z",
    download_url: "http://example.com/report2.pdf",
  },
  {
    id: "3",
    report_type: "Rapport mensuel",
    period: "Janvier 2024",
    generated_at: "2024-02-29T08:15:00Z",
    download_url: "http://example.com/report3.pdf",
  },
];

afterEach(() => {
  vi.restoreAllMocks();
  Reflect.deleteProperty(globalThis, "fetch");
});

describe("ReportsList", () => {
  it("renders reports with pagination", async () => {
    const user = userEvent.setup();
    render(<ReportsList reports={sampleReports} pageSize={2} />);

    expect(screen.getByText(/Rapport quotidien/i)).toBeInTheDocument();
    expect(screen.getByText(/Rapport hebdomadaire/i)).toBeInTheDocument();
    expect(screen.queryByText(/Rapport mensuel/i)).not.toBeInTheDocument();

    const nextButton = screen.getByRole("button", { name: /suivant/i });
    await user.click(nextButton);

    expect(screen.getByText(/Rapport mensuel/i)).toBeInTheDocument();
    const previousButton = screen.getByRole("button", { name: /précédent/i });
    expect(previousButton).not.toBeDisabled();
  });

  it("triggers a download when clicking the action button", async () => {
    const blob = new Blob(["pdf"], { type: "application/pdf" });
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      blob: () => Promise.resolve(blob),
    });
    globalThis.fetch = fetchMock;

    const urlApi = globalThis.URL || window.URL;
    const hadCreate = typeof urlApi.createObjectURL === "function";
    const hadRevoke = typeof urlApi.revokeObjectURL === "function";
    if (!hadCreate) {
      urlApi.createObjectURL = () => "";
    }
    if (!hadRevoke) {
      urlApi.revokeObjectURL = () => {};
    }
    const createSpy = vi
      .spyOn(urlApi, "createObjectURL")
      .mockReturnValue("blob://download");
    const revokeSpy = vi
      .spyOn(urlApi, "revokeObjectURL")
      .mockImplementation(() => {});
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});

    const user = userEvent.setup();
    render(
      <ReportsList
        reports={[
          {
            id: "99",
            report_type: "Rapport hebdomadaire",
            generated_at: "2024-02-10T10:00:00Z",
            download_url: "http://example.com/report.pdf",
            filename: "report.pdf",
          },
        ]}
      />
    );

    const downloadButton = screen.getByRole("button", { name: /télécharger/i });
    await user.click(downloadButton);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://example.com/report.pdf",
      expect.objectContaining({ headers: expect.any(Object) })
    );
    expect(createSpy).toHaveBeenCalled();
    expect(revokeSpy).toHaveBeenCalled();
    expect(clickSpy).toHaveBeenCalled();
    expect(downloadButton).not.toBeDisabled();

    createSpy.mockRestore();
    revokeSpy.mockRestore();
    clickSpy.mockRestore();
    if (!hadCreate) {
      delete urlApi.createObjectURL;
    }
    if (!hadRevoke) {
      delete urlApi.revokeObjectURL;
    }
  });
});
