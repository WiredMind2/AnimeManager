import { PAGE_SIZE } from "./config";
import {
  PAGE_SIZE_OPTIONS,
  isPageSizeOption,
  type PageSizeOption,
} from "./library";

export { PAGE_SIZE, PAGE_SIZE_OPTIONS, isPageSizeOption, type PageSizeOption };

export function safeBrowsePage(value: string | undefined): number {
  const parsed = Number.parseInt(value ?? "1", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
}

export function resolveBrowsePageSize(param: string | undefined): PageSizeOption {
  const fromParam = Number.parseInt(param ?? "", 10);
  if (fromParam === 50) return 48;
  if (isPageSizeOption(fromParam)) return fromParam;
  return PAGE_SIZE;
}

export function browseOffset(page: number, pageSize: number): number {
  return Math.max(0, (Math.max(1, page) - 1) * pageSize);
}

export type BrowsePageParams = {
  page?: number;
  size?: PageSizeOption;
};

export function withBrowsePage(
  baseUrl: string,
  params: BrowsePageParams,
  defaultSize: PageSizeOption = PAGE_SIZE,
): string {
  const url = new URL(baseUrl, "http://local.invalid");
  const page = params.page ?? 1;
  if (page > 1) url.searchParams.set("page", String(page));
  else url.searchParams.delete("page");

  const size = params.size ?? defaultSize;
  if (size !== defaultSize) url.searchParams.set("size", String(size));
  else url.searchParams.delete("size");

  const qs = url.searchParams.toString();
  return qs ? `${url.pathname}?${qs}` : url.pathname;
}
