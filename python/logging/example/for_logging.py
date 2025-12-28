import json
import logging
import logging.config
from typing import Optional, Dict
from jinja2 import Template, Environment, FileSystemLoader
from pathlib import Path
from pydantic import BaseModel


class LoggerTemplate:
    template_filepath: Path
    template_filename: str
    template_path: str
    template: Optional[Template]

    def __init__(self, template_filename: str):
        self.template_filepath: Path = Path(template_filename)
        self.template_path, self.template_filename = str(self.template_filepath.parent), str(self.template_filepath.name)

        file_loader = FileSystemLoader(self.template_path)
        env = Environment(loader=file_loader)

        self.template = env.get_template(self.template_filename) if self.template_filepath.is_file() else None

    def render(self, tdata) -> Dict:
        if self.template:
            return json.loads(self.template.render(tdata=tdata))
        else:
            return {}


class LoggerINFO_TemplateContext(BaseModel):
    run_id: str
    test_name: Optional[str] = None
    logging_dir: Optional[str] = None
    artefact_local_dir: Optional[str] = None

class ArtefactSummaryFormatter(logging.Formatter):
    def __init__(self, datefmt=None):
        super().__init__(datefmt=datefmt)

    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()
        asctime = self.formatTime(record, self.datefmt)

        mode = getattr(record, "mode", "default")  # из extra

        if mode == "header":
            return f"## <header> {asctime} — {record.message}"
        elif mode == "line":
            return f"- <line> {asctime} [{record.levelname}] {record.message}"
        elif mode == "verbose":
            return f"<verbose> {asctime} | {record.levelname} | {record.name} | {record.message}"
        else:
            return f"<other> {asctime} | {record.levelname} | {record.message}"

if __name__ == "__main__":
    template_base: LoggerTemplate = LoggerTemplate(template_filename="config_logging_info.j2")
    loggerINFO_TemplateContext = LoggerINFO_TemplateContext(
        run_id = "r123"
    )
    dictConfig = template_base.render(tdata=loggerINFO_TemplateContext)
    print(json.dumps(dictConfig, indent=2))

    logging.config.dictConfig(dictConfig)

    log = logging.getLogger("artefact_logger")
    h = logging.LoggerAdapter(log, {"mode": "header"})
    l = logging.LoggerAdapter(log, {"mode": "line"})
    v = logging.LoggerAdapter(log, {"mode": "verbose"})
    o = logging.LoggerAdapter(log)


    h.info("header")
    l.info("line")
    v.info("verbose")
    o.info("other")





