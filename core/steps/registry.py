class StepRegistry:
    _registry = {}

    @classmethod
    def register(cls, step_type, step_class):
        cls._registry[step_type] = step_class

    @classmethod
    def get_step_class(cls, step_type):
        return cls._registry.get(step_type)

    @classmethod
    def create_step(cls, step_type, config, context):
        step_class = cls.get_step_class(step_type)
        if step_class:
            return step_class(config, context)
        return None
