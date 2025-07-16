/* Remove braces from single-statement blocks in JS code

Most LLMs generate code with braces around single-statement blocks like this:

if (condition) {
  do_something();
}

... while I prefer:

if (condition) do_something();

This is an extension to jscodeshift that removes such braces.

Usage:

npx jscodeshift -t unbrace.js --extensions=js filename.js

I've added this as an `unbrace` abbr in setup.fish.
*/

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
