package org.pantsbuild.tools.junit.lib;

import org.junit.Test;

public class SecStaticSysExitTestCase {
  static {
    System.out.println("<<<<<<<<<<<<<<<<<<<<<<<<<<<<static clinit called");
    System.exit(0);
  }

  @Test
  public void passingTest() {

  }

  @Test
  public void passingTest2() {

  }
}
