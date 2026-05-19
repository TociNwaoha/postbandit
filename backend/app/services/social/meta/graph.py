from __future__ import annotations

import json

import httpx


class GraphRequestError(Exception):
    pass


def extract_graph_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except (ValueError, json.JSONDecodeError):
        payload = {}

    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            for key in ("error_user_msg", "message", "type", "code", "error_subcode"):
                value = error.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()[:240]
                if isinstance(value, int):
                    return str(value)
        for key in ("error_description", "error_message", "error"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:240]

    return f"http_{response.status_code}"


def graph_get(
    client: httpx.Client,
    *,
    url: str,
    params: dict | None = None,
    headers: dict | None = None,
) -> dict:
    try:
        response = client.get(url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPStatusError as exc:
        raise GraphRequestError(extract_graph_error(exc.response)) from exc
    except httpx.RequestError as exc:
        raise GraphRequestError("Graph request failed. Please retry.") from exc

    if not isinstance(data, dict):
        raise GraphRequestError("Graph response was invalid")
    return data


def graph_post(
    client: httpx.Client,
    *,
    url: str,
    data: dict | None = None,
    json_body: dict | None = None,
    headers: dict | None = None,
) -> dict:
    cleaned_data = None
    if isinstance(data, dict):
        cleaned_data = {key: value for key, value in data.items() if value is not None}

    cleaned_json = None
    if isinstance(json_body, dict):
        cleaned_json = {key: value for key, value in json_body.items() if value is not None}

    try:
        response = client.post(url, data=cleaned_data, json=cleaned_json, headers=headers)
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPStatusError as exc:
        raise GraphRequestError(extract_graph_error(exc.response)) from exc
    except httpx.RequestError as exc:
        raise GraphRequestError("Graph request failed. Please retry.") from exc

    if not isinstance(payload, dict):
        raise GraphRequestError("Graph response was invalid")
    return payload
