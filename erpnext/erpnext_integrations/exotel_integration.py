import frappe
import requests

# api/method/erpnext.erpnext_integrations.exotel_integration.handle_incoming_call
# api/method/erpnext.erpnext_integrations.exotel_integration.handle_end_call
# api/method/erpnext.erpnext_integrations.exotel_integration.handle_missed_call


@frappe.whitelist(allow_guest=True)
def handle_incoming_call(**kwargs):
	try:
		exotel_settings = get_exotel_settings()
		if not exotel_settings.enabled:
			return

		call_payload = kwargs
		status = call_payload.get("Status")
		if status == "free":
			return

		call_log = get_call_log(call_payload)
		if not call_log:
			create_call_log(call_payload)
		else:
			update_call_log(call_payload, call_log=call_log)
	except Exception:
		frappe.db.rollback()
		exotel_settings.log_error("Error in Exotel incoming call")
		frappe.db.commit()


@frappe.whitelist(allow_guest=True)
def handle_end_call(**kwargs):
	update_call_log(kwargs, "Completed")


@frappe.whitelist(allow_guest=True)
def handle_missed_call(**kwargs):
	status = ""
	call_type = kwargs.get("CallType")
	dial_call_status = kwargs.get("DialCallStatus")

	if call_type == "incomplete" and dial_call_status == "no-answer":
		status = "No Answer"
	elif call_type == "client-hangup" and dial_call_status == "canceled":
		status = "Canceled"
	elif call_type == "incomplete" and dial_call_status == "failed":
		status = "Failed"

	update_call_log(kwargs, status)


def update_call_log(call_payload, status="Ringing", call_log=None):
	call_log = call_log or get_call_log(call_payload)

	# for a new sid, call_log and get_call_log will be empty so create a new log
	if not call_log:
		call_log = create_call_log(call_payload)
	if call_log:
		call_log.status = status
		call_log.to = call_payload.get("DialWhomNumber")
		call_log.duration = call_payload.get("DialCallDuration") or 0
		call_log.recording_url = call_payload.get("RecordingUrl")
		call_log.save(ignore_permissions=True)
		frappe.db.commit()
		return call_log


def get_call_log(call_payload):
	call_log_id = call_payload.get("CallSid")
	if frappe.db.exists("Call Log", call_log_id):
		return frappe.get_doc("Call Log", call_log_id)


def create_call_log(call_payload):
	call_log = frappe.new_doc("Call Log")
	call_log.id = call_payload.get("CallSid")
	call_log.to = call_payload.get("DialWhomNumber")
	call_log.medium = call_payload.get("To")
	call_log.status = "Ringing"
	setattr(call_log, "from", call_payload.get("CallFrom"))
	call_log.save(ignore_permissions=True)
	frappe.db.commit()
	return call_log


@frappe.whitelist()
def get_call_status(call_id):
	endpoint = get_exotel_endpoint(f"Calls/{call_id}.json")
	response = requests.get(endpoint)
	status = response.json().get("Call", {}).get("Status")
	return status


@frappe.whitelist()
def make_a_call(from_number, to_number, caller_id):
	endpoint = get_exotel_endpoint("Calls/connect.json?details=true")
	response = requests.post(endpoint, data={"From": from_number, "To": to_number, "CallerId": caller_id})

	return response.json()


def get_exotel_settings():
	return frappe.get_single("Exotel Settings")


def whitelist_numbers(numbers, caller_id):
	endpoint = get_exotel_endpoint("CustomerWhitelist")
	response = requests.post(
		endpoint,
		data={
			"VirtualNumber": caller_id,
			"Number": numbers,
		},
	)

	return response


def get_all_exophones():
	endpoint = get_exotel_endpoint("IncomingPhoneNumbers")
	response = requests.post(endpoint)
	return response


def get_exotel_endpoint(action):
	settings = get_exotel_settings()
	return "https://{api_key}:{api_token}@api.exotel.com/v1/Accounts/{sid}/{action}".format(
		api_key=settings.api_key, api_token=settings.api_token, sid=settings.account_sid, action=action
	)
