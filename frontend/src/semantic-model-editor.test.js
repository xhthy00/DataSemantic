import assert from "node:assert/strict";
import test from "node:test";
import {
  fieldList,
  semanticEditorMarkup,
  renderSemanticSummary,
} from "./semantic-model-editor.js";

test("composite dimension keys retain order", () => {
  assert.deepEqual(fieldList("school_id， exam_id, subject_id"), [
    "school_id",
    "exam_id",
    "subject_id",
  ]);
});

test("imported names are escaped and retired metadata does not produce UI", () => {
  const obj = {
    name: "<img src=x onerror=alert(1)>",
    properties: { analysisContract: { schemaVersion: 1 } },
  };
  const html = semanticEditorMarkup(obj, {}) + renderSemanticSummary(obj);
  assert.ok(!html.includes("<img"));
  assert.ok(!html.includes("V1"));
  assert.ok(!html.includes("analysisContract"));
  assert.ok(!html.includes("edit-view-contract"));
  assert.match(html, /edit-semantic-model/);
});
