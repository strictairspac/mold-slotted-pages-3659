import { api } from "../api/workbench.js";
import { errorText, field } from "../components/common/fields.js";
import { empty, pageHeading, section } from "../components/common/panel.js";
import { resultTable } from "../components/common/table.js";
import { submit } from "../hooks/submit.js";
import { el } from "../utils/dom.js";
import { cell, download, time } from "../utils/format.js";

function reviewForm(id, saved) {
  const form = el("form", {id: "review-form"},
    field("复核意见", el("textarea", {name: "note", required: true, minlength: 3, maxlength: 500, rows: 3})),
    errorText(), el("button", {type: "submit"}, "签署复核"));
  submit(form, async values => saved(await api.submitReview(id, {note: values.get("note")})));
  return form;
}

function signature(review) {
  return el("div", {"data-testid": "reviewed", class: "signature"},
    el("strong", {}, `已签署 · ${review.actor}`), el("p", {}, review.note), el("time", {}, time(review.created_at)));
}

function archivePanel(run, user, issue) {
  const box = el("div", {class: "stack", "data-testid": "archive"});

  async function render() {
    let archived = null;
    try {
      archived = await api.archiveDetail(run.id);
    } catch {
      archived = null;
    }
    if (archived) {
      const reclaim = el("p", {class: "help"},
        `地址段 ${archived.digest.slice(0, 12)}… · ${archived.size} 字节 · 共 ${archived.references} 个批次引用` +
        (archived.references > 1 ? "，其他批次仍在使用，清理本批次不会回收。" : "，清理本批次后回收。"));
      const clean = el("button", {type: "button", onclick: async () => {
        clean.disabled = true;
        issue.textContent = "";
        try {
          await api.purgeArchive(run.id);
          await render();
        } catch (error) {
          issue.textContent = error.message;
          clean.disabled = false;
        }
      }}, "清理本批次归档");
      box.replaceChildren(
        el("strong", {}, "已归档，与其他批次共用一份地址段"),
        reclaim,
        el("div", {class: "actions"},
          el("button", {type: "button", onclick: async () => {
            try {
              await download(await api.archiveDownload(run.id), `segment-${archived.digest}.json`);
            } catch (error) {
              issue.textContent = error.message;
            }
          }}, "下载归档地址段"),
          user.role === "operator" ? clean : null));
      return;
    }
    const act = el("button", {type: "button", onclick: async () => {
      act.disabled = true;
      issue.textContent = "";
      try {
        await api.archive(run.id);
        await render();
      } catch (error) {
        issue.textContent = error.message;
        act.disabled = false;
      }
    }}, "归档地址段");
    box.replaceChildren(
      el("p", {class: "help", "data-testid": "unarchived"},
        "归档后本批次只保留自身操作记录，相同地址段与其他批次共用一份，下载内容保持不变。"),
      user.role === "operator" ? act : empty("等待资料操作员归档。"));
  }

  render();
  return box;
}

export async function evidencePage(config, user, route) {
  const runs = (await api.runs()).filter(item => item.status === "done");
  const chosen = route.id ?? runs[0]?.id;
  const run = chosen ? await api.run(chosen) : null;
  if (!run?.result) return el("div", {class: "page"},
    pageHeading(config.modules[3], null), empty("成功执行一个批次后可以查看、签核和下载证据。"),
    el("a", {href: "#runs"}, config.modules[2]));

  const review = await api.review(run.id);
  const issue = errorText();
  const button = el("button", {type: "button", onclick: async () => {
    button.disabled = true;
    issue.textContent = "";
    try {
      await download(await api.export(run.id), `evidence-${run.id}.json`);
    } catch (error) {
      issue.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  }}, "导出证据");
  const signing = el("div", {});
  signing.append(review ? signature(review) : user.role === "reviewer" ?
    reviewForm(run.id, data => signing.replaceChildren(signature(data))) : empty("待复核员签署。"));
  const options = el("select", {"aria-label": "选择已完成的批次", onchange: event => {
    location.hash = `evidence/${event.target.value}`;
  }}, runs.map(item => el("option", {value: item.id, selected: item.id === run.id}, `#${item.id} ${item.case_title}`)));
  return el("div", {class: "page evidence"},
    pageHeading(config.modules[3], run.case_title, button),
    issue, options,
    el("section", {class: "feature evidence-summary"}, el("div", {}, el("h2", {}, "批次判定"), el("p", {}, run.result.summary)),
      el("details", {}, el("summary", {}, "证据摘要"), el("code", {}, run.digest))),
    el("dl", {class: "metrics"}, Object.entries(run.result.metrics).map(([label, value]) =>
      el("div", {}, el("dt", {}, label), el("dd", {}, cell(value))))),
    section("业务结果明细", run.result.rows.length ? resultTable(run.result.rows) : empty("此批次无明细。")),
    section("追溯地址归档", archivePanel(run, user, issue)),
    section("复核签署", signing));
}
