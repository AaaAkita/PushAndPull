from core.utils import resolve_selector, replace_variables

class StepContext:
    """
    Holds the execution environment for a step.
    """
    def __init__(self, page, logger, row, stop_flag, execution_logs):
        self.page = page
        self.logger = logger # Function to log messages
        self.row = row       # Current data row (dict)
        self.stop_flag = stop_flag # Threading event
        self.execution_logs = execution_logs

class BaseStep:
    """
    Abstract base class for a single automation step.
    """
    def __init__(self, step_config, context: StepContext):
        self.config = step_config
        self.context = context

    def log(self, message, level="INFO"):
        self.context.logger(message, level)

    def execute(self):
        """
        Execute the step logic.
        Returns:
            bool: True if success, False if failed.
        """
        raise NotImplementedError("Steps must implement execute()")

    def should_stop(self):
        return self.context.stop_flag.is_set()

    def replace_vars(self, text):
        return replace_variables(text, self.context.row)

    def resolve_sel(self, selector):
        return resolve_selector(selector)

    def get_timeout(self, default=30000):
        val = self.config.get('timeout')
        if val is not None:
             try:
                 return int(val)
             except:
                 pass
        return default
