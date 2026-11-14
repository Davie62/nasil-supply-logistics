def security_context(request):
    return {"csp_nonce": getattr(request, "csp_nonce", "")}
