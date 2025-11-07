# FR-19: Recover functions for deleted boards and columns

This PR will implement recovery functionality for deleted boards and columns.

## Planned Changes
- Add soft delete (deleted_at) to boards and columns tables
- Update delete operations to soft delete
- Add recovery methods and commands
- Create UI flows for recovery

See feature request #19 for details.
