from .instruments import GenericValidator, IIRSValidator, OHRCValidator, TMC2Validator

VALIDATORS = [
    OHRCValidator(),
    TMC2Validator(),
    IIRSValidator(),
    GenericValidator(),
]


def validate_instrument(path, metadata, context):
    for validator in VALIDATORS:
        matched, _reason = validator.matches(path, metadata, context)
        if matched:
            return validator.validate(path, metadata, context)
    return GenericValidator().validate(path, metadata, context)


def supported_instruments():
    return ["OHRC", "TMC-2", "IIRS"]
