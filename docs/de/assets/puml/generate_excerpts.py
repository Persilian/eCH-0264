"""Generate excerpts of the hand-drawn PlantUML data models.

The modelling decisions of the documentation are shown next to small
excerpts of the conceptual or logical data model. Instead of drawing these
excerpts by hand, they are generated from the full models, so that they always
match them.

A YAML file lists the excerpts, for example:

    gliederung:
      source: conceptual_model.puml   # relative to the YAML file
      classes: [KP, GE]                # PlantUML aliases to keep
      notes: false                     # optional, default true
      skip: [ersetzt]                  # optional, relation labels to drop

Usage (from the repository root, after "make setup" or "make docs" has
installed PlantUML and Java into the virtual environment):

    venv/bin/python docs/de/assets/puml/generate_excerpts.py

Run it again whenever a model or excerpts.yml changes, and commit the
generated files: the excerpts are not built by the Makefile, so that the
Makefile of the semantic-web-template stays unchanged.

For each excerpt, the script writes <name>.puml to the output directory and
renders it to <name>.svg with PlantUML. It
keeps the header (skinparams, pragmas), the selected classes and enumerations
inside their packages, the relations between selected classes (except those
whose label is listed under "skip") and the notes attached to them. Hidden
layout links and the legend are dropped.

PlantUML's own "remove"/"restore" does not work with the Smetana layout
engine for classes inside packages, which is why the excerpts are generated.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

import yaml

PACKAGE_RE = re.compile(r'^\s*package\s+"(?P<label>[^"]*)"\s+as\s+(?P<alias>\w+)\s*\{\s*$')
ENTITY_RE = re.compile(r'^\s*(?:abstract\s+class|class|enum|interface)\s+"[^"]*"\s+as\s+(?P<alias>\w+)\b')
NOTE_RE = re.compile(r'^\s*note\s+\w+\s+of\s+(?P<alias>\w+)\s*$')
RELATION_RE = re.compile(
    r'^\s*(?P<left>\w+)\s+(?:"[^"]*"\s+)?'
    r'(?P<arrow>[<>*o|.#x}+^]*[-.][^\s"]*)\s+'
    r'(?:"[^"]*"\s+)?(?P<right>\w+)\s*(?::.*)?$'
)


def relation_label(relation):
    """Label of a relation line ("A --> B : label"), or an empty string."""
    return relation.split(":", 1)[1].strip() if ":" in relation else ""


def indent(lines, prefix):
    """Lines of an entity or note block: first and last line at the given
    prefix, the lines in between indented by two more spaces."""
    if len(lines) == 1:
        return [prefix + lines[0]]
    return [prefix + lines[0], *(prefix + "  " + line for line in lines[1:-1]), prefix + lines[-1]]


class Model:
    """The parts of a PlantUML class diagram needed to build excerpts."""

    def __init__(self, path):
        self.header = []        # lines between @startuml and the first package
        self.packages = {}      # alias -> label
        self.entities = {}      # alias -> (package alias or None, lines)
        self.relations = []     # (left, right, line)
        self.notes = []         # (alias, lines)
        self._parse(Path(path).read_text(encoding="utf-8").splitlines())

    def _parse(self, lines):
        in_header = False
        package = None
        block = None            # ("entity" | "note", alias, lines)
        depth = 0               # brace depth inside an entity block
        in_legend = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("@startuml"):
                in_header = True
                continue
            if stripped.startswith("@enduml"):
                break
            if in_legend:
                in_legend = not stripped.startswith("endlegend")
                continue
            if block is not None:
                block[2].append(line.strip())
                if block[0] == "entity":
                    depth += line.count("{") - line.count("}")
                    if depth <= 0:
                        self.entities[block[1]] = (package, block[2])
                        block = None
                elif stripped == "end note":
                    self.notes.append((block[1], block[2]))
                    block = None
                continue
            if not stripped or stripped.startswith("'"):
                continue
            if stripped.startswith("legend"):
                in_legend = True
                continue
            match = PACKAGE_RE.match(line)
            if match:
                in_header = False
                package = match["alias"]
                self.packages[package] = match["label"]
                continue
            if in_header:
                self.header.append(line)
                continue
            if stripped == "}" and package is not None:
                package = None
                continue
            match = ENTITY_RE.match(line)
            if match:
                if "{" in line and "}" not in line:
                    block, depth = ("entity", match["alias"], [line.strip()]), 1
                else:
                    self.entities[match["alias"]] = (package, [line.strip()])
                continue
            match = NOTE_RE.match(line)
            if match:
                block = ("note", match["alias"], [line.strip()])
                continue
            match = RELATION_RE.match(line)
            if match and "[hidden]" not in match["arrow"]:
                self.relations.append((match["left"], match["right"], line.strip()))

    def excerpt(self, aliases, notes=True, skip=()):
        """PlantUML source of an excerpt with the given class aliases."""
        unknown = [alias for alias in aliases if alias not in self.entities]
        if unknown:
            raise ValueError(f"unknown aliases: {', '.join(unknown)}")
        selected = set(aliases)
        out = ["@startuml", *self.header]
        for package, label in self.packages.items():
            members = [a for a in aliases if self.entities[a][0] == package]
            if not members:
                continue
            out.append(f'package "{label}" as {package} {{')
            for alias in members:
                out.extend(indent(self.entities[alias][1], "  "))
            out.append("}")
        out.extend(line for alias in aliases if self.entities[alias][0] is None
                   for line in self.entities[alias][1])
        out.extend(line for left, right, line in self.relations
                   if left in selected and right in selected and relation_label(line) not in skip)
        if notes:
            for alias, lines in self.notes:
                if alias in selected:
                    out.extend(indent(lines, ""))
        out.append("@enduml")
        return "\n".join(out) + "\n"


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]   # docs/de/assets/puml -> repository root


def main():
    parser = argparse.ArgumentParser(description="Generate excerpts of PlantUML data models.")
    parser.add_argument("-s", "--spec", default=HERE / "excerpts.yml", help="YAML file listing the excerpts")
    parser.add_argument("-o", "--output", default=HERE.parent / "excerpts", help="output directory")
    parser.add_argument("--java", default=ROOT / "venv/java17/jdk-17.0.2/bin/java", help="Java executable")
    parser.add_argument("--plantuml", default=ROOT / "venv/bin/plantuml.jar", help="PlantUML jar")
    args = parser.parse_args()

    spec_path = Path(args.spec)
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    models = {}
    for name, entry in spec.items():
        source = spec_path.parent / entry["source"]
        model = models.setdefault(source, Model(source))
        try:
            text = model.excerpt(entry["classes"], entry.get("notes", True), entry.get("skip", ()))
        except ValueError as error:
            sys.exit(f"Excerpt '{name}' of {source}: {error}")
        (output / f"{name}.puml").write_text(text, encoding="utf-8")

    # Excerpts removed from the YAML file: delete their old .puml and .svg.
    for stale in list(output.glob("*.puml")) + list(output.glob("*.svg")):
        if stale.stem not in spec:
            stale.unlink()

    pumls = sorted(str(path) for path in output.glob("*.puml"))
    subprocess.run([str(args.java), "-jar", str(args.plantuml), "-tsvg", *pumls], check=True)
    print(f"Generated and rendered {len(spec)} excerpts in {output}")


if __name__ == "__main__":
    main()
