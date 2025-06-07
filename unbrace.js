// Remove braces from single-statement blocks in JS code
//
// Usage:
// npx jscodeshift -t unbrace.js --extensions=js filename.js
module.exports = (fileInfo, { j }) => {
  const root = j(fileInfo.source);

  root
    .find(j.BlockStatement)
    .filter((path) => path.node.body.length === 1) // single-statement block
    .forEach((path) => {
      const parent = path.parent.node;
      const stmt = path.node.body[0];

      const isBody = (child) => child === path.node; // helper
      if (
        (j.IfStatement.check(parent) && isBody(parent.consequent)) ||
        (j.ForStatement.check(parent) && isBody(parent.body)) ||
        (j.ForInStatement.check(parent) && isBody(parent.body)) ||
        (j.ForOfStatement.check(parent) && isBody(parent.body)) ||
        (j.WhileStatement.check(parent) && isBody(parent.body)) ||
        (j.DoWhileStatement.check(parent) && isBody(parent.body))
      )
        j(path).replaceWith(stmt); // unwrap!;
    });

  return root.toSource({ quote: "single" });
};
