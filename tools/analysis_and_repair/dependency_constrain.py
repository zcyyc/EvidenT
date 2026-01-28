from collections import defaultdict


class SpecParser:
    def __init__(self, path):
        self.path = path
        self.macros = {}
        self.metadata = {}
        self.requires = []
        self.build_requires = []
        self.provides = []
        self.sections = defaultdict(str)

    def parse(self):
        current_section = None
        buffer = []

        with open(self.path, encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()

                # 跳过空行和注释
                if not line or line.startswith("#"):
                    continue

                # 宏定义
                if line.startswith("%define") or line.startswith("%global"):
                    parts = line.split(maxsplit=2)
                    if len(parts) == 3:
                        self.macros[parts[1]] = parts[2]
                    continue

                # 元信息键值对
                if ":" in line and not line.startswith("%"):
                    key, value = line.split(":", 1)
                    key = key.strip()
                    value = value.strip()
                    if key.lower() == "requires":
                        self.requires.append(value)
                    elif key.lower() == "buildrequires":
                        self.build_requires.append(value)
                    elif key.lower() == "provides":
                        self.provides.append(value)
                    else:
                        self.metadata[key] = value
                    continue

                # 新的 section
                if line.startswith("%"):
                    # 保存上一个 section
                    if current_section and buffer:
                        self.sections[current_section] = "\n".join(buffer).strip()
                        buffer = []
                    current_section = line.split()[0]  # e.g. "%prep"
                    continue

                # 普通行，加入当前 section
                if current_section:
                    buffer.append(raw_line.rstrip())

        # 收尾保存最后一个 section
        if current_section and buffer:
            self.sections[current_section] = "\n".join(buffer).strip()

    def to_dict(self):
        return {
            "macros": self.macros,
            "metadata": self.metadata,
            "requires": self.requires,
            "build_requires": self.build_requires,
            "provides": self.provides,
            "sections": dict(self.sections),
        }


def spec_parser_main(spec_path):
    parser = SpecParser(spec_path)
    parser.parse()
    data = parser.to_dict()

    return data
