import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { Pagination } from "./Pagination";

afterEach(cleanup);

it("navigates between pages and stops at the first and last", () => {
  const change = vi.fn();
  const data = { count: 51, page_size: 25 };
  const view = render(<Pagination page={1} data={data} onChange={change} />);
  const previous = () => screen.getByRole("button", { name: "Previous" }) as HTMLButtonElement;
  const next = () => screen.getByRole("button", { name: "Next" }) as HTMLButtonElement;
  expect(previous().disabled).toBe(true);
  fireEvent.click(previous());
  expect(change).not.toHaveBeenCalled();
  fireEvent.click(next());
  expect(change).toHaveBeenLastCalledWith(2);

  view.rerender(<Pagination page={2} data={data} onChange={change} />);
  expect(previous().disabled).toBe(false);
  expect(next().disabled).toBe(false);
  fireEvent.click(next());
  expect(change).toHaveBeenLastCalledWith(3);

  view.rerender(<Pagination page={3} data={data} onChange={change} />);
  expect(next().disabled).toBe(true);
  fireEvent.click(previous());
  expect(change).toHaveBeenLastCalledWith(2);
});

it.each([undefined, { count: 0, page_size: 25 }, { count: 25, page_size: 25 }])(
  "has no extra page while loading or when results fit on one page: %j", (data) => {
    render(<Pagination page={1} data={data} onChange={vi.fn()} />);
    for (const button of screen.getAllByRole("button")) {
      expect((button as HTMLButtonElement).disabled).toBe(true);
    }
  },
);
