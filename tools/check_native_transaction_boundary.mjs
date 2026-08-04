import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import ts from "typescript";

const ADAPTER = "src/infrastructure/sqlite/plugin-sql-adapter.ts";
const ADAPTER_MODULE = "@/infrastructure/sqlite/plugin-sql-adapter";
const EXECUTOR_CONSUMERS = new Set([
  "src/features/clients/sqlite-client-catalog.ts",
  "src/features/projects/sqlite-project-catalog.ts",
  "src/features/tasks/sqlite-task-catalog.ts",
]);
const EXECUTOR_EXPORTS = new Set([
  "IndependentSqlStatementExecutor",
  "getIndependentSqlStatementExecutor",
]);
const TRANSACTION_VERBS = new Set([
  "BEGIN",
  "COMMIT",
  "ROLLBACK",
  "SAVEPOINT",
  "RELEASE",
  "END",
]);

const root = resolveRoot(process.argv.slice(2));
const errors = [];

for (const file of productionTypeScriptFiles(path.join(root, "src"))) {
  inspectFile(file);
}

if (errors.length > 0) {
  for (const error of errors) console.error(error);
  process.exitCode = 1;
} else {
  console.log("Native transaction boundary check passed.");
}

function resolveRoot(arguments_) {
  if (arguments_.length === 0) return process.cwd();
  if (arguments_.length === 2 && arguments_[0] === "--root") {
    return path.resolve(arguments_[1]);
  }
  console.error("Usage: node tools/check_native_transaction_boundary.mjs [--root PATH]");
  process.exit(2);
}

function productionTypeScriptFiles(directory) {
  if (!fs.existsSync(directory)) return [];
  const files = [];
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) files.push(...productionTypeScriptFiles(target));
    else if (
      /\.tsx?$/.test(entry.name) &&
      !/\.test\.tsx?$/.test(entry.name) &&
      !entry.name.endsWith(".d.ts")
    ) {
      files.push(target);
    }
  }
  return files.sort();
}

function inspectFile(file) {
  const relative = path.relative(root, file).split(path.sep).join("/");
  const source = ts.createSourceFile(
    file,
    fs.readFileSync(file, "utf8"),
    ts.ScriptTarget.Latest,
    true,
    file.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
  );
  const executeAliases = new Set();

  function report(node, message) {
    const position = source.getLineAndCharacterOfPosition(node.getStart(source));
    errors.push(`${relative}:${position.line + 1}:${position.character + 1}: ${message}`);
  }

  function visit(node) {
    if (ts.isImportDeclaration(node) && ts.isStringLiteral(node.moduleSpecifier)) {
      inspectImport(node, relative, report);
    }
    if (relative !== ADAPTER && ts.isCallExpression(node)) {
      inspectExecuteCall(node, executeAliases, report);
    }
    if (relative !== ADAPTER && ts.isVariableDeclaration(node)) {
      inspectExecuteAlias(node, executeAliases);
    }
    ts.forEachChild(node, visit);
  }

  visit(source);
}

function inspectImport(node, relative, report) {
  const moduleName = node.moduleSpecifier.text;
  if (moduleName === "@tauri-apps/plugin-sql" && relative !== ADAPTER) {
    report(node, `plugin-sql may be imported only by ${ADAPTER}`);
  }
  if (!isAdapterModule(moduleName, relative) || !node.importClause?.namedBindings) return;
  if (ts.isNamespaceImport(node.importClause.namedBindings)) {
    if (!EXECUTOR_CONSUMERS.has(relative)) {
      report(node, "namespace adapter import can access the independent SQL executor");
    }
    return;
  }
  if (!ts.isNamedImports(node.importClause.namedBindings)) return;

  const importsExecutor = node.importClause.namedBindings.elements.some((element) =>
    EXECUTOR_EXPORTS.has((element.propertyName ?? element.name).text),
  );
  if (importsExecutor && !EXECUTOR_CONSUMERS.has(relative)) {
    report(node, "independent SQL executor import is not reviewed for this module");
  }
}

function isAdapterModule(moduleName, importingFile) {
  if (moduleName === ADAPTER_MODULE) return true;
  if (!moduleName.startsWith(".")) return false;
  const resolved = path.posix.normalize(
    path.posix.join(path.posix.dirname(importingFile), moduleName),
  );
  return resolved === ADAPTER.slice(0, -3) || resolved === ADAPTER;
}

function inspectExecuteCall(node, executeAliases, report) {
  if (ts.isIdentifier(node.expression) && executeAliases.has(node.expression.text)) {
    report(node, "calling independent SQL execute through an alias is forbidden");
    return;
  }
  if (!isExecuteAccess(node.expression)) return;

  const argument = node.arguments[0];
  if (
    !argument ||
    (!ts.isStringLiteral(argument) && !ts.isNoSubstitutionTemplateLiteral(argument))
  ) {
    report(node, "independent SQL must be one static string literal");
    return;
  }
  const sql = argument.text;
  if (hasMultipleStatements(sql)) {
    report(node, "independent SQL must contain exactly one statement");
    return;
  }
  const verb = firstSqlVerb(sql);
  if (verb && TRANSACTION_VERBS.has(verb)) {
    report(node, `transaction-control statement ${verb} is forbidden`);
  }
}

function inspectExecuteAlias(node, executeAliases) {
  const initializer = node.initializer;
  if (
    ts.isIdentifier(node.name) &&
    initializer &&
    (isExecuteAccess(initializer) ||
      (ts.isIdentifier(initializer) && executeAliases.has(initializer.text)))
  ) {
    executeAliases.add(node.name.text);
  }
  if (
    initializer &&
    ts.isCallExpression(initializer) &&
    ts.isPropertyAccessExpression(initializer.expression) &&
    initializer.expression.name.text === "bind" &&
    ts.isPropertyAccessExpression(initializer.expression.expression) &&
    initializer.expression.expression.name.text === "execute"
  ) {
    if (ts.isIdentifier(node.name)) executeAliases.add(node.name.text);
  }
  if (ts.isObjectBindingPattern(node.name)) {
    for (const element of node.name.elements) {
      if ((element.propertyName ?? element.name).getText() === "execute") {
        if (ts.isIdentifier(element.name)) executeAliases.add(element.name.text);
      }
    }
  }
}

function isExecuteAccess(node) {
  return (
    (ts.isPropertyAccessExpression(node) && node.name.text === "execute") ||
    (ts.isElementAccessExpression(node) &&
      node.argumentExpression &&
      ts.isStringLiteral(node.argumentExpression) &&
      node.argumentExpression.text === "execute")
  );
}

function hasMultipleStatements(sql) {
  let quote;
  let lineComment = false;
  let blockComment = false;
  for (let index = 0; index < sql.length; index += 1) {
    const character = sql[index];
    const next = sql[index + 1];
    if (lineComment) {
      if (character === "\n") lineComment = false;
      continue;
    }
    if (blockComment) {
      if (character === "*" && next === "/") {
        blockComment = false;
        index += 1;
      }
      continue;
    }
    if (quote) {
      if (character === quote) {
        if (next === quote) index += 1;
        else quote = undefined;
      }
      continue;
    }
    if (character === "-" && next === "-") {
      lineComment = true;
      index += 1;
    } else if (character === "/" && next === "*") {
      blockComment = true;
      index += 1;
    } else if (character === "'" || character === '"' || character === "`") {
      quote = character;
    } else if (character === ";" && stripSqlTrivia(sql.slice(index + 1)).length > 0) {
      return true;
    }
  }
  return false;
}

function stripSqlTrivia(sql) {
  let remaining = sql.trimStart();
  while (remaining.length > 0) {
    if (remaining.startsWith("--")) {
      const newline = remaining.indexOf("\n");
      remaining = newline < 0 ? "" : remaining.slice(newline + 1).trimStart();
    } else if (remaining.startsWith("/*")) {
      const end = remaining.indexOf("*/", 2);
      if (end < 0) return "";
      remaining = remaining.slice(end + 2).trimStart();
    } else {
      return remaining;
    }
  }
  return remaining;
}

function firstSqlVerb(sql) {
  let remaining = sql.trimStart();
  while (remaining.length > 0) {
    if (remaining.startsWith("--")) {
      const newline = remaining.indexOf("\n");
      remaining = newline < 0 ? "" : remaining.slice(newline + 1).trimStart();
    } else if (remaining.startsWith("/*")) {
      const end = remaining.indexOf("*/", 2);
      remaining = end < 0 ? "" : remaining.slice(end + 2).trimStart();
    } else {
      return /^[A-Za-z]+/.exec(remaining)?.[0]?.toUpperCase();
    }
  }
  return undefined;
}
