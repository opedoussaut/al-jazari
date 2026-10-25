import { render, screen } from "@testing-library/react";
import Answer, { linkEvidence } from "./Answer";

test("evidence markers become in-page links", () => {
  expect(linkEvidence("39 joints [E1][E2].", "m1")).toBe("39 joints [E1](#ev-m1-E1)[E2](#ev-m1-E2).");
});

test("renders markdown tables and evidence badges", () => {
  render(<Answer text={"| a | b |\n|---|---|\n| 1 | 2 |\n\nSee [E3]."} messageId="x" />);
  expect(screen.getByRole("table")).toBeTruthy();
  expect(screen.getByText("E3").getAttribute("href")).toBe("#ev-x-E3");
});
