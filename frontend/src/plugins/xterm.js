import 'xterm/dist/xterm.css'

import { Terminal } from 'xterm'
import * as fit from 'xterm/lib/addons/fit/fit'
import * as attach from 'xterm/lib/addons/attach/attach'
import * as fullscreen from 'xterm/lib/addons/fullscreen/fullscreen';

Terminal.applyAddon(fullscreen);  // Apply the `fullscreen` addon
Terminal.applyAddon(fit)
Terminal.applyAddon(attach)
 
export default Terminal