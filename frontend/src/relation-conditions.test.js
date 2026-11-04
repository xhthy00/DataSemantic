import assert from "node:assert/strict";
import test from "node:test";
import {
  buildRelationCondition,
  parseRelationCondition,
  relationColumns,
} from "./relation-conditions.js";

const models = [
  {
    name: "scores",
    columns: [
      { name: "school_id" },
      { name: "year" },
      { name: "school", relationship: "schools" },
    ],
  },
  { name: "schools", columns: [{ name: "id" }, { name: "year" }] },
];

test("round-trips multiple selected fields as quoted SQL", () => {
  const rows = [
    { from: "school_id", operator: "=", to: "id" },
    { from: "year", operator: "=", to: "year" },
  ];
  const condition = buildRelationCondition(rows, "scores", "schools", models);
  assert.equal(
    condition,
    '"scores"."school_id" = "schools"."id" AND "scores"."year" = "schools"."year"',
  );
  assert.deepEqual(
    parseRelationCondition(condition, "scores", "schools"),
    rows,
  );
});

test("loads legacy SQL with parentheses, quoting and reversed comparisons", () => {
  assert.deepEqual(
    parseRelationCondition(
      '((schools.id = scores.school_id) and (`schools`.`year` = "scores"."year"))',
      "scores",
      "schools",
    ),
    [
      { from: "school_id", operator: "=", to: "id" },
      { from: "year", operator: "=", to: "year" },
    ],
  );
});

test("complex or malformed SQL is never partially converted", () => {
  for (const condition of [
    "scores.year != schools.year",
    "scores.year >= schools.year",
    "scores.school_id = schools.id OR scores.year = schools.year",
    "scores.school_id = schools.id AND schools.year = 2026",
    "CAST(scores.school_id AS integer) = schools.id",
    "scores.school_id = schools.id -- comment",
    "scores.school_id = schools.id;",
    "(scores.school_id = schools.id",
    "scores.school_id = unknown.id",
  ])
    assert.equal(
      parseRelationCondition(condition, "scores", "schools"),
      null,
      condition,
    );
  assert.deepEqual(parseRelationCondition("", "scores", "schools"), []);
  assert.equal(parseRelationCondition(42, "scores", "schools"), null);
});

test("rejects incomplete, duplicate, navigation, stale fields and invalid models", () => {
  const valid = { from: "school_id", operator: "=", to: "id" };
  for (const rows of [
    [],
    [{ ...valid, from: "" }],
    [{ ...valid, to: "removed" }],
    [{ ...valid, from: "school" }],
    [{ ...valid, operator: "OR" }],
    [valid, valid],
  ])
    assert.throws(() =>
      buildRelationCondition(rows, "scores", "schools", models),
    );
  assert.throws(() =>
    buildRelationCondition([valid], "scores", "scores", models),
  );
  assert.equal(relationColumns(models[0]).length, 2);
});
