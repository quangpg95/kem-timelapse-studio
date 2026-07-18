from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from kem_timelapse.domain.errors import ErrorCode, PipelineError
from kem_timelapse.jobs.runner import JobRunner
from kem_timelapse.storage.project_repository import ProjectRepository

app = typer.Typer(help="Internal diagnostics and pipeline control for Kem Timelapse Studio.")

RunnerFactory = Callable[[Path, Sequence[Path], bool], JobRunner]
_runner_factory: RunnerFactory | None = None


def configure_runner_factory(factory: RunnerFactory) -> None:
    """Install the composition root shared by desktop and internal CLI entry points."""
    global _runner_factory
    _runner_factory = factory


def _runner_for_project(
    project_dir: Path,
    sources: Sequence[Path] = (),
    overwrite: bool = False,
) -> JobRunner:
    if _runner_factory is None:
        raise PipelineError(
            ErrorCode.TIMELINE_INVALID,
            "pipeline services are not configured",
            context={"project": project_dir.name},
        )
    return _runner_factory(project_dir, sources, overwrite)


def _exit_for(error: BaseException) -> NoReturn:
    if isinstance(error, PipelineError):
        payload = {
            "code": error.code.value,
            "message": str(error),
            "context": error.context,
        }
        typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True), err=True)
        raise typer.Exit(2)
    if isinstance(error, InterruptedError):
        typer.echo(json.dumps({"code": "Cancelled", "message": str(error)}), err=True)
        raise typer.Exit(130)
    typer.echo(
        json.dumps(
            {"code": "UnexpectedFailure", "message": str(error)},
            ensure_ascii=False,
            sort_keys=True,
        ),
        err=True,
    )
    raise typer.Exit(1)


@app.command("inspect")
def inspect_project(project_dir: Path) -> None:
    """Print checkpoint state without loading UI or media services."""
    try:
        state = ProjectRepository(project_dir).load_state()
    except Exception as error:
        _exit_for(error)
    payload = {
        "status": state.status.value,
        "resume_from": state.resume_from.value if state.resume_from is not None else None,
        "completed_analysis_clip_ids": state.completed_analysis_clip_ids,
        "completed_variants": [variant.value for variant in state.completed_variants],
        "warning_codes": state.warning_codes,
    }
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


@app.command()
def analyze(
    project_dir: Path,
    source: Annotated[
        list[Path] | None,
        typer.Option("--source", help="Source recording; repeat as needed."),
    ] = None,
) -> None:
    """Analyze selected source clips and create the three review timelines."""
    try:
        _runner_for_project(project_dir, source or ()).analyze_to_review()
    except Exception as error:
        _exit_for(error)


@app.command()
def render(
    project_dir: Path,
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace invalid old outputs."),
) -> None:
    """Render or resume the three-variant Content Pack."""
    try:
        _runner_for_project(project_dir, overwrite=overwrite).render_pack()
    except Exception as error:
        _exit_for(error)


if __name__ == "__main__":
    app()
