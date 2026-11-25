import { request } from "./http.js";

export const api = {
  config: () => request("/workbench"),
  login: data => request("/auth/login", {method: "POST", data}),
  cases: () => request("/cases"),
  createCase: data => request("/cases", {method: "POST", data}),
  runs: () => request("/runs"),
  run: (id, signal) => request(`/runs/${id}`, {signal}),
  enqueue: (id, data) => request(`/cases/${id}/runs`, {method: "POST", data}),
  review: id => request(`/runs/${id}/review`),
  submitReview: (id, data) => request(`/runs/${id}/review`, {method: "POST", data}),
  export: id => request(`/runs/${id}/export`, {raw: true}),
  segments: () => request("/segments"),
  archive: id => request(`/runs/${id}/archive`, {method: "POST"}),
  archiveDetail: id => request(`/runs/${id}/archive`),
  archiveDownload: id => request(`/runs/${id}/archive/download`, {raw: true}),
  purgeArchive: id => request(`/runs/${id}/archive`, {method: "DELETE"}),
  audit: () => request("/audit", {signal: AbortSignal.timeout(5000)}),
};
