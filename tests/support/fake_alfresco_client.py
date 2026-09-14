class FakeAlfrescoClient:

    instances = []

    def __init__(self, ticket=None):
        self.ticket = ticket
        self.checklists = []
        self.findings = []
        self.evidence = []
        self.followup_reports = []
        self.followup_evidence = []
        self.batch_active = False
        self.rollback_count = 0
        FakeAlfrescoClient.instances.append(self)

    def begin_batch(self):
        self.batch_active = True

    def rollback_batch(self):
        self.rollback_count += 1
        self.batch_active = False

    def store_checklist_document(self, checklist):
        self.checklists.append(checklist)

    def store_finding_document(self, finding):
        self.findings.append(finding)

    def store_evidence_file(self, specialty_name, evidence_file):
        self.evidence.append((specialty_name, evidence_file.name))

    def store_followup_report_document(self, report, specialty_name):
        finding_id = report["followUpReport"]["findingId"]
        sequence = len(self.followup_reports) + 1
        self.followup_reports.append((specialty_name, report))
        return {
            "storedFilename": f"FollowUp {finding_id} {sequence:02d}.json"
        }

    def store_followup_evidence_file(self, specialty_name, evidence_file):
        self.followup_evidence.append((specialty_name, evidence_file.name))
