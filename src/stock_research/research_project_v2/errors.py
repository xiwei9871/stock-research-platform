class ResearchProjectV2Error(ValueError):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = {} if details is None else details
