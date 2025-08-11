(function() {
  const API_BASE = '/api';
  
  // State
  let devices = [];
  let editingDevice = null;
  
  // Elements
  const deviceGrid = document.getElementById('deviceGrid');
  const messageArea = document.getElementById('messageArea');
  const addDeviceBtn = document.getElementById('addDeviceBtn');
  const deviceModal = document.getElementById('deviceModal');
  const deleteModal = document.getElementById('deleteModal');
  const deviceForm = document.getElementById('deviceForm');
  const modalTitle = document.getElementById('modalTitle');
  
  // Form fields
  const deviceName = document.getElementById('deviceName');
  const deviceHostname = document.getElementById('deviceHostname');
  const deviceType = document.getElementById('deviceType');
  const deviceUsername = document.getElementById('deviceUsername');
  const devicePassword = document.getElementById('devicePassword');
  const devicePort = document.getElementById('devicePort');
  const deviceEnabled = document.getElementById('deviceEnabled');
  const deviceNxapi = document.getElementById('deviceNxapi');
  
  // Modal buttons
  const closeModalBtn = document.getElementById('closeModalBtn');
  const cancelBtn = document.getElementById('cancelBtn');
  const closeDeleteModalBtn = document.getElementById('closeDeleteModalBtn');
  const cancelDeleteBtn = document.getElementById('cancelDeleteBtn');
  const confirmDeleteBtn = document.getElementById('confirmDeleteBtn');
  const deleteDeviceName = document.getElementById('deleteDeviceName');
  
  // Utility functions
  function showMessage(message, type = 'info') {
    const className = type === 'error' ? 'error-message' : 'success-message';
    messageArea.innerHTML = `<div class="${className}">${message}</div>`;
    setTimeout(() => {
      messageArea.innerHTML = '';
    }, 5000);
  }
  
  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }
  
  // API functions
  async function fetchDevices() {
    try {
      const response = await fetch(`${API_BASE}/devices?all_devices=true`);
      if (!response.ok) throw new Error('Failed to fetch devices');
      devices = await response.json();
      renderDevices();
    } catch (error) {
      showMessage('Failed to load devices: ' + error.message, 'error');
    }
  }
  
  async function saveDevice(deviceData) {
    const method = editingDevice ? 'PUT' : 'POST';
    const url = editingDevice 
      ? `${API_BASE}/devices/${editingDevice.name}`
      : `${API_BASE}/devices`;
    
    try {
      const response = await fetch(url, {
        method: method,
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(deviceData)
      });
      
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to save device');
      }
      
      showMessage(`Device ${deviceData.name} ${editingDevice ? 'updated' : 'created'} successfully`, 'success');
      closeDeviceModal();
      fetchDevices();
    } catch (error) {
      showMessage('Failed to save device: ' + error.message, 'error');
    }
  }
  
  async function deleteDevice(deviceName) {
    try {
      const response = await fetch(`${API_BASE}/devices/${deviceName}`, {
        method: 'DELETE'
      });
      
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to delete device');
      }
      
      showMessage(`Device ${deviceName} deleted successfully`, 'success');
      fetchDevices();
    } catch (error) {
      showMessage('Failed to delete device: ' + error.message, 'error');
    }
  }
  
  // UI functions
  function renderDevices() {
    if (devices.length === 0) {
      deviceGrid.innerHTML = '<div style="padding: 2rem; text-align: center; color: #6699cc;">No devices configured. Click the + button to add a device.</div>';
      return;
    }
    
    deviceGrid.innerHTML = devices.map(device => `
      <div class="device-card">
        <div class="device-status ${device.enabled ? 'enabled' : 'disabled'}">
          ${device.enabled ? 'Enabled' : 'Disabled'}
        </div>
        <h3>${escapeHtml(device.name)}</h3>
        <div class="device-info">
          <div class="device-info-row">
            <span class="device-info-label">Hostname:</span>
            <span class="device-info-value">${escapeHtml(device.hostname)}</span>
          </div>
          <div class="device-info-row">
            <span class="device-info-label">Type:</span>
            <span class="device-info-value">${escapeHtml(device.device_type)}</span>
          </div>
          <div class="device-info-row">
            <span class="device-info-label">Username:</span>
            <span class="device-info-value">${escapeHtml(device.username)}</span>
          </div>
          <div class="device-info-row">
            <span class="device-info-label">Port:</span>
            <span class="device-info-value">${device.port}</span>
          </div>
          <div class="device-info-row">
            <span class="device-info-label">NX-API:</span>
            <span class="device-info-value">${device.use_nxapi ? 'Yes' : 'No'}</span>
          </div>
        </div>
        <div class="device-actions">
          <button class="btn btn-primary" onclick="editDevice('${escapeHtml(device.name)}')">Edit</button>
          <button class="btn btn-danger" onclick="confirmDelete('${escapeHtml(device.name)}')">Delete</button>
        </div>
      </div>
    `).join('');
  }
  
  function openDeviceModal(device = null) {
    editingDevice = device;
    modalTitle.textContent = device ? 'Edit Device' : 'Add Device';
    
    if (device) {
      deviceName.value = device.name;
      deviceHostname.value = device.hostname;
      deviceType.value = device.device_type;
      deviceUsername.value = device.username;
      devicePassword.value = '';
      devicePort.value = device.port;
      deviceEnabled.checked = device.enabled;
      deviceNxapi.checked = device.use_nxapi;
      deviceName.disabled = true; // Can't change name when editing
    } else {
      deviceForm.reset();
      devicePort.value = '22';
      deviceEnabled.checked = true;
      deviceName.disabled = false;
    }
    
    deviceModal.classList.add('show');
  }
  
  function closeDeviceModal() {
    deviceModal.classList.remove('show');
    editingDevice = null;
    deviceForm.reset();
  }
  
  function openDeleteModal(name) {
    deleteDeviceName.textContent = name;
    deleteModal.classList.add('show');
  }
  
  function closeDeleteModal() {
    deleteModal.classList.remove('show');
  }
  
  // Global functions for onclick handlers
  window.editDevice = function(name) {
    const device = devices.find(d => d.name === name);
    if (device) {
      openDeviceModal(device);
    }
  };
  
  window.confirmDelete = function(name) {
    openDeleteModal(name);
  };
  
  // Event listeners
  addDeviceBtn.addEventListener('click', () => openDeviceModal());
  closeModalBtn.addEventListener('click', closeDeviceModal);
  cancelBtn.addEventListener('click', closeDeviceModal);
  closeDeleteModalBtn.addEventListener('click', closeDeleteModal);
  cancelDeleteBtn.addEventListener('click', closeDeleteModal);
  
  confirmDeleteBtn.addEventListener('click', () => {
    const name = deleteDeviceName.textContent;
    closeDeleteModal();
    deleteDevice(name);
  });
  
  deviceForm.addEventListener('submit', (e) => {
    e.preventDefault();
    
    const deviceData = {
      name: deviceName.value,
      hostname: deviceHostname.value,
      device_type: deviceType.value,
      username: deviceUsername.value,
      port: parseInt(devicePort.value),
      enabled: deviceEnabled.checked,
      use_nxapi: deviceNxapi.checked
    };
    
    // Only include password if it's provided
    if (devicePassword.value) {
      deviceData.password = devicePassword.value;
    } else if (!editingDevice) {
      // Password is required for new devices
      showMessage('Password is required for new devices', 'error');
      return;
    }
    
    saveDevice(deviceData);
  });
  
  // Close modals when clicking outside
  window.addEventListener('click', (e) => {
    if (e.target === deviceModal) {
      closeDeviceModal();
    }
    if (e.target === deleteModal) {
      closeDeleteModal();
    }
  });
  
  // Initialize
  fetchDevices();
})();